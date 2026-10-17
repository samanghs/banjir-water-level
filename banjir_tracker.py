import os
import requests
import urllib3
import pandas as pd
from datetime import datetime

# Suppress SSL certificate warnings common on Malaysian .gov portals
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Target District: 5 corresponds to Kuala Langat (change to -1 for all Selangor stations)
DISTRICT_ID = 5
BASE_CONFIG_URL = "https://infobanjirjps.selangor.gov.my/data/config.json"
CSV_FILE = "selangor_water_level_data.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*"
}

def fetch_water_data():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str}] Fetching data from InfoBanjir JPS API...")

    # 1. Fetch dynamic API base URL from config.json
    try:
        cfg_resp = requests.get(BASE_CONFIG_URL, headers=HEADERS, timeout=15, verify=False)
        cfg_resp.raise_for_status()
        api_base = cfg_resp.json().get("apiURL", "https://infobanjirjps.selangor.gov.my/InfoBanjir.WebAPI/api/")
    except Exception as e:
        print(f"Config fetch failed ({e}), using default fallback endpoint.")
        api_base = "https://infobanjirjps.selangor.gov.my/InfoBanjir.WebAPI/api/"

    if not api_base.endswith("/"):
        api_base += "/"

    # 2. Query station river levels for the specified district
    if DISTRICT_ID == -1:
        data_url = f"{api_base}StationRiverLevels/GetWLStationData/-1"
    else:
        data_url = f"{api_base}StationRiverLevels/GetWLAllStationData/{DISTRICT_ID}"

    print(f"Requesting: {data_url}")
    resp = requests.get(data_url, headers=HEADERS, timeout=25, verify=False)
    resp.raise_for_status()
    payload = resp.json()

    stations = payload.get("stations", [])
    if not stations:
        print("No station records returned.")
        return None

    # 3. Extract relevant measurement fields
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

    # Filter out empty readings if a sensor is currently null/offline
    new_df = new_df.dropna(subset=["Water_Level_m"])

    if os.path.exists(CSV_FILE) and os.path.getsize(CSV_FILE) > 0:
        existing_df = pd.read_csv(CSV_FILE)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        # Avoid duplicate readings using Station_ID and timestamp
        combined = combined.drop_duplicates(subset=["Station_ID", "Last_Updated"], keep="last")
        added = len(combined) - len(existing_df)
        combined.to_csv(CSV_FILE, index=False)
        print(f"Appended {added} new reading(s). Total rows: {len(combined)}")
    else:
        new_df.to_csv(CSV_FILE, index=False)
        print(f"Initialized {CSV_FILE} with {len(new_df)} records.")

if __name__ == "__main__":
    data = fetch_water_data()
    save_and_deduplicate(data)
