import os
import time
import requests
import urllib3
import pandas as pd
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DISTRICT_ID = 5
BASE_CONFIG_URL = "https://infobanjirjps.selangor.gov.my/data/config.json"
CSV_FILE = "selangor_water_level_data.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*"
}

def fetch_with_retry(url, retries=3, backoff=5):
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30, verify=False)
            resp.raise_for_status()
            return resp.json()
        except Exception as err:
            print(f"[Attempt {attempt}/{retries}] Request failed: {err}")
            if attempt < retries:
                time.sleep(backoff)
            else:
                return None

def fetch_water_data():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] Fetching data from InfoBanjir JPS API...")

    cfg_data = fetch_with_retry(BASE_CONFIG_URL)
    api_base = cfg_data.get("apiURL", "https://infobanjirjps.selangor.gov.my/InfoBanjir.WebAPI/api/") if cfg_data else "https://infobanjirjps.selangor.gov.my/InfoBanjir.WebAPI/api/"

    if not api_base.endswith("/"):
        api_base += "/"

    data_url = (
        f"{api_base}StationRiverLevels/GetWLStationData/-1"
        if DISTRICT_ID == -1
        else f"{api_base}StationRiverLevels/GetWLAllStationData/{DISTRICT_ID}"
    )

    payload = fetch_with_retry(data_url)
    if not payload:
        print("Government portal did not respond after 3 attempts. Skipping this run.")
        return None

    stations = payload.get("stations", [])
    if not stations:
        print("No station records returned.")
        return None

    records = []
    for s in stations:
        records.append({
            "Station_ID": str(s.get("stationId", "")).strip(),
            "Station_Name": s.get("stationName", "").strip(),
            "District": s.get("districtName", "").strip(),
            "Last_Updated": s.get("lastUpdate", ""),
            "Water_Level_m": s.get("waterLevel"),
            "Normal_Threshold_m": s.get("wlth_normal"),
            "Alert_Threshold_m": s.get("wlth_alert"),
            "Warning_Threshold_m": s.get("wlth_warning"),
            "Danger_Threshold_m": s.get("wlth_danger"),
            "Latitude": s.get("latitude"),
            "Longitude": s.get("longitude"),
            "Scraped_At": now_str
        })

    return pd.DataFrame(records)

def save_and_deduplicate(new_df):
    if new_df is None or new_df.empty:
        return

    new_df = new_df.dropna(subset=["Water_Level_m"])

    existing_df = pd.DataFrame()
    if os.path.exists(CSV_FILE):
        try:
            existing_df = pd.read_csv(CSV_FILE)
        except pd.errors.EmptyDataError:
            # Handles 0-byte or blank files cleanly without crashing
            print(f"{CSV_FILE} was empty. Overwriting with fresh data.")
            existing_df = pd.DataFrame()

    if not existing_df.empty:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Station_ID", "Last_Updated"], keep="last")
        added = len(combined) - len(existing_df)
        combined.to_csv(CSV_FILE, index=False)
        print(f"Appended {added} new reading(s). Total records: {len(combined)}")
    else:
        new_df.to_csv(CSV_FILE, index=False)
        print(f"Created {CSV_FILE} with {len(new_df)} initial records.")

if __name__ == "__main__":
    data = fetch_water_data()
    save_and_deduplicate(data)
