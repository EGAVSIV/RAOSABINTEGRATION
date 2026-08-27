import json
from pathlib import Path
import pandas as pd

# =====================================================
# LOCAL REPOSITORY PATH CONFIGURATION
# =====================================================
# Resolves the root directory relative to this script (fib/ -> root)
BASE_DIR = Path(__file__).resolve().parent.parent

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
OUTPUT_JSON_FILE = BASE_DIR / "results.json"


def get_symbols_from_local_folder(folder_path: Path):
    """Fetches all stock symbol file names from the local data folder."""
    if not folder_path.exists() or not folder_path.is_dir():
        print(f"Warning: Local folder '{folder_path}' does not exist.")
        return []

    # Extract symbol names from .json files (e.g., 'AAPL.json' -> 'AAPL')
    symbols = [f.stem for f in folder_path.glob("*.json")]
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

    for tf_label, folder_name in TIMEFRAME_MAP.items():
        all_results[tf_label] = {}
        folder_path = BASE_DIR / folder_name
        
        print(f"Scanning local files for {tf_label} ({folder_name})...")
        symbols = get_symbols_from_local_folder(folder_path)
        print(f"Found {len(symbols)} symbols in {folder_name}.")

        for lookback in LOOKBACK_LEVELS:
            all_results[tf_label][lookback] = {}

            for fib_key in FIB_OPTIONS.keys():
                scanned_stocks = []

                for symbol in symbols:
                    json_file_path = folder_path / f"{symbol}.json"

                    try:
                        with open(json_file_path, "r", encoding="utf-8") as f:
                            raw_data = json.load(f)
                    except Exception as e:
                        print(f"Error reading {json_file_path}: {e}")
                        continue

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

    with open(OUTPUT_JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print(f"Calculation Complete! Results saved to {OUTPUT_JSON_FILE}")


if __name__ == "__main__":
    run_engine()
