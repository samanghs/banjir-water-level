import os
import time
import requests
import urllib3
import pandas as pd
from datetime import datetime

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DISTRICT_ID = 5
BASE_CONFIG_URL = "https://infobanjirjps.selangor.gov.my/data/config.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*"
}

def get_monthly_csv_filename():
    """Generates filename based on current year and month (e.g., selangor_water_level_data_2026_10.csv)"""
    year_month = datetime.now().strftime("%Y_%m")
    return f"selangor_water_level_data_{year_month}.csv"

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
        print("Government portal did not respond after 3 attempts.")
        return None

    stations = payload.get("stations", [])
    if not stations:
        print("No station records returned.")
        return None

    records = []
    for s in stations:
        if s.get("stationStatus") != 1:
            continue

        wl = s.get("waterLevel")
        if wl is None or wl <= -900:
            continue

        records.append({
            "Station_ID": str(s.get("stationId", "")).strip(),
            "Station_Name": s.get("stationName", "").strip(),
            "District": s.get("districtName", "").strip(),
            "Last_Updated": s.get("lastUpdate", ""),
            "Water_Level_m": wl,
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
        print("No valid active station records to write.")
        return

    # Determine target file for the current month
    csv_file = get_monthly_csv_filename()

    existing_df = pd.DataFrame()
    if os.path.exists(csv_file):
        try:
            existing_df = pd.read_csv(csv_file)
            if "Water_Level_m" in existing_df.columns:
                existing_df = existing_df[existing_df["Water_Level_m"] > -900]
        except pd.errors.EmptyDataError:
            existing_df = pd.DataFrame()

    if not existing_df.empty:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Station_ID", "Last_Updated"], keep="last")
        added = len(combined) - len(existing_df)
        combined.to_csv(csv_file, index=False)
        print(f"Appended {added} new reading(s) to {csv_file}. Total records: {len(combined)}")
    else:
        new_df.to_csv(csv_file, index=False)
        print(f"Created {csv_file} with {len(new_df)} initial records.")

if __name__ == "__main__":
    data = fetch_water_data()
    save_and_deduplicate(data)
