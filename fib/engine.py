import json
import urllib.request
import pandas as pd

# =====================================================
# DATA COLLECTOR REPO CONFIGURATION
# =====================================================
REPO_OWNER = "EGAVSIV"
REPO_NAME = "Data-Collector"
BRANCH = "main"

# API endpoint for reading folder contents
API_BASE_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents"

# Raw content endpoint for fetching actual JSON file data
RAW_BASE_URL = f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}/{BRANCH}"

TIMEFRAME_MAP = {
    "15 Min": "stockdata_15",
    "1 Hour": "stockdata_1H",
    "Daily": "stockdata_D",
    "Weekly": "stockdata_W",
    "Monthly": "stockdata_M",
}

FIB_OPTIONS = {
    "61-78": (0.61, 0.78),
    "58-61": (0.58, 0.61),
    "35-50": (0.35, 0.50),
}

LOOKBACK_LEVELS = [50, 100, 200]
OUTPUT_JSON_FILE = "results.json"


def fetch_url_json(url: str):
    """Helper function to fetch JSON data from a remote URL."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        return None


def get_symbols_from_repo_folder(folder_name: str):
    """Dynamically fetches all stock symbol file names from the Data-Collector folder via GitHub API."""
    url = f"{API_BASE_URL}/{folder_name}?ref={BRANCH}"
    folder_contents = fetch_url_json(url)

    if not folder_contents or not isinstance(folder_contents, list):
        print(f"Warning: Could not fetch symbol list for folder '{folder_name}'")
        return []

    # Extract symbol names from .json files (e.g., 'AAPL.json' -> 'AAPL')
    symbols = [
        item["name"].replace(".json", "")
        for item in folder_contents
        if item.get("name", "").endswith(".json")
    ]
    return sorted(symbols)


def calculate_fib_levels(df: pd.DataFrame, lookback: int, fib_key: str):
    df_slice = df.tail(lookback)
    high_price = df_slice["high"].max()
    low_price = df_slice["low"].min()

    if high_price == low_price:
        return None

    diff = high_price - low_price
    r1, r2 = FIB_OPTIONS[fib_key]

    level1 = high_price - (diff * r1)
    level2 = high_price - (diff * r2)

    return min(level1, level2), max(level1, level2)


def run_engine():
    all_results = {}

    for tf_label, folder in TIMEFRAME_MAP.items():
        all_results[tf_label] = {}
        print(f"Fetching symbols for {tf_label} ({folder})...")
        
        # Dynamically pull symbol list from Data Collector Repo
        symbols = get_symbols_from_repo_folder(folder)
        print(f"Found {len(symbols)} symbols in {folder}.")

        for lookback in LOOKBACK_LEVELS:
            all_results[tf_label][lookback] = {}

            for fib_key in FIB_OPTIONS.keys():
                scanned_stocks = []

                for symbol in symbols:
                    # Construct direct HTTP URL to raw JSON file in Data-Collector repo
                    raw_file_url = f"{RAW_BASE_URL}/{folder}/{symbol}.json"
                    raw_data = fetch_url_json(raw_file_url)

                    if not raw_data:
                        continue

                    df = pd.DataFrame(raw_data)
                    df.columns = [c.lower() for c in df.columns]

                    if "date" in df.columns:
                        df["date"] = pd.to_datetime(df["date"])
                        df = df.sort_values("date")

                    if len(df) < lookback:
                        continue

                    levels = calculate_fib_levels(df, lookback, fib_key)
                    if levels is None:
                        continue

                    zone_low, zone_high = levels
                    current_close = df["close"].iloc[-1]

                    if zone_low <= current_close <= zone_high:
                        scanned_stocks.append(
                            {
                                "Stock": symbol,
                                "Close": round(float(current_close), 2),
                                "ZoneLow": round(float(zone_low), 2),
                                "ZoneHigh": round(float(zone_high), 2),
                            }
                        )

                all_results[tf_label][lookback][fib_key] = scanned_stocks

    with open(OUTPUT_JSON_FILE, "w") as f:
        json.dump(all_results, f, indent=2)

    print(f"Calculation Complete! Results saved to {OUTPUT_JSON_FILE}")


if __name__ == "__main__":
    run_engine()
