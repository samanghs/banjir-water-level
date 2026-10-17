import os
import io
import requests
import pandas as pd
from bs4 import BeautifulSoup
from datetime import datetime

URL = "https://publicinfobanjir.water.gov.my/aras-air/data-paras-air/?state=SEL&type=NEGERI&lang=en"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

CSV_FILE = "selangor_water_level_data.csv"

def fetch_water_data():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Scraping InfoBanjir...")
    response = requests.get(URL, headers=HEADERS, timeout=25)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    tables = pd.read_html(io.StringIO(str(soup)))

    if not tables:
        print("No table found.")
        return None

    df = tables[0]

    # Clean multi-level headers if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            " ".join(col).strip() if "Unnamed" not in col[1] else col[0].strip()
            for col in df.columns
        ]

    df.columns = [str(c).strip() for c in df.columns]
    df["Scraped_At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return df

def save_and_deduplicate(new_df):
    if new_df is None or new_df.empty:
        print("Empty dataframe; nothing to save.")
        return

    id_col = [c for c in new_df.columns if "Station ID" in c or "Station" in c]
    time_col = [c for c in new_df.columns if "Updated" in c or "Last" in c]

    if os.path.exists(CSV_FILE):
        existing_df = pd.read_csv(CSV_FILE)
        combined = pd.concat([existing_df, new_df], ignore_index=True)

        if id_col and time_col:
            combined = combined.drop_duplicates(subset=[id_col[0], time_col[0]], keep="last")
        else:
            combined = combined.drop_duplicates()

        added = len(combined) - len(existing_df)
        combined.to_csv(CSV_FILE, index=False)
        print(f"Appended {added} new records. Total: {len(combined)}")
    else:
        new_df.to_csv(CSV_FILE, index=False)
        print(f"Created {CSV_FILE} with {len(new_df)} records.")

if __name__ == "__main__":
    df = fetch_water_data()
    save_and_deduplicate(df)