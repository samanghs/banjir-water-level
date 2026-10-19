import os
import time
import requests
import urllib3
import pandas as pd
from datetime import datetime, timezone, timedelta

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Malaysia Time Zone (UTC+8)
MYT = timezone(timedelta(hours=8))

# District IDs: 1 to 9 covers all of Selangor
DISTRICT_IDS = [1, 2, 3, 4, 5, 6, 7, 8, 9]

BASE_CONFIG_URL = "https://infobanjirjps.selangor.gov.my/data/config.json"
DEFAULT_API_BASE = "https://infobanjirjps.selangor.gov.my/InfoBanjir.WebAPI/api/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*"
}

def get_monthly_csv_filename():
    """Generates file name based on Malaysia local year and month."""
    now_myt = datetime.now(MYT)
    return f"selangor_water_level_data_{now_myt.strftime('%Y_%m')}.csv"

def fetch_json(session, url, retries=3, backoff=3):
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, headers=HEADERS, timeout=25, verify=False)
            resp.raise_for_status()
            return resp.json()
        except Exception as err:
            print(f"[Attempt {attempt}/{retries}] Failed for {url}: {err}")
            if attempt < retries:
                time.sleep(backoff)
            else:
                return None

def fetch_all_districts_data():
    now_myt = datetime.now(MYT)
    now_str = now_myt.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now_str} MYT] Starting data collection across all districts...")

    session = requests.Session()

    # Discover API base URL
    cfg_data = fetch_json(session, BASE_CONFIG_URL)
    api_base = cfg_data.get("apiURL", DEFAULT_API_BASE) if cfg_data else DEFAULT_API_BASE
    if not api_base.endswith("/"):
        api_base += "/"

    all_records = []

    for district_id in DISTRICT_IDS:
        data_url = f"{api_base}StationRiverLevels/GetWLAllStationData/{district_id}"
        payload = fetch_json(session, data_url)

        if not payload:
            print(f"District {district_id}: No response from server.")
            continue

        stations = payload.get("stations", [])
        valid_district_count = 0

        for s in stations:
            wl = s.get("waterLevel")

            # Ignore null readings or sensor offline codes (-9999)
            # Legitimate negative readings (e.g. -0.38 m) are kept
            if wl is None or wl <= -900:
                continue

            all_records.append({
                "Station_ID": str(s.get("stationId", "")).strip(),
                "Station_Name": s.get("stationName", "").strip(),
                "District": s.get("districtName", "").strip(),
                "Last_Updated": s.get("lastUpdate", "").strip(),
                "Water_Level_m": float(wl),
                "Normal_Threshold_m": s.get("wlth_normal"),
                "Alert_Threshold_m": s.get("wlth_alert"),
                "Warning_Threshold_m": s.get("wlth_warning"),
                "Danger_Threshold_m": s.get("wlth_danger"),
                "Latitude": s.get("latitude"),
                "Longitude": s.get("longitude"),
                "Scraped_At": now_str
            })
            valid_district_count += 1

        print(f"District {district_id}: Collected {valid_district_count} active readings.")

    return pd.DataFrame(all_records)

def save_and_deduplicate(new_df):
    if new_df is None or new_df.empty:
        print("No valid active station records gathered.")
        return

    csv_file = get_monthly_csv_filename()
    existing_df = pd.DataFrame()

    if os.path.exists(csv_file):
        try:
            existing_df = pd.read_csv(csv_file, dtype={"Station_ID": str})
            if "Water_Level_m" in existing_df.columns:
                existing_df = existing_df[existing_df["Water_Level_m"] > -900]
        except pd.errors.EmptyDataError:
            existing_df = pd.DataFrame()

    if not existing_df.empty:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        # Prevent identical readings from creating duplicate rows
        combined = combined.drop_duplicates(subset=["Station_ID", "Last_Updated"], keep="last")
        added = len(combined) - len(existing_df)
        combined.to_csv(csv_file, index=False)
        print(f"Appended {added} new reading(s) to {csv_file}. Total rows: {len(combined)}")
    else:
        new_df.to_csv(csv_file, index=False)
        print(f"Created {csv_file} with {len(new_df)} initial records.")

if __name__ == "__main__":
    df = fetch_all_districts_data()
    save_and_deduplicate(df)
