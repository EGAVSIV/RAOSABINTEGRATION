import os
import ssl
import socket
import time
import pandas as pd
from tvDatafeed import TvDatafeed, Interval

# === TV Datafeed Login via Env Variables ===
# Set TV_USERNAME and TV_PASSWORD in GitHub Repository Secrets
username = os.environ.get("TV_USERNAME", "EGAVSIV")
password = os.environ.get("TV_PASSWORD", "Eric$1234")

# Initialize headless mode (set username/password to None for guest access if needed)
tv = TvDatafeed(username=username, password=password)

# === Timeframes ===
interval_map = {
    'D': Interval.in_daily,
    'W': Interval.in_weekly,
    'M': Interval.in_monthly
}

# === Output Folder ===
output_dir = "Broad_index_data"
os.makedirs(output_dir, exist_ok=True)

retry_delay = 3
max_attempts = 5  # Prevents GitHub Actions hanging indefinitely

def fetch_with_retry(symbol, label, interval):
    attempt = 1
    while attempt <= max_attempts:
        try:
            df = tv.get_hist(symbol=symbol, exchange='NSE', interval=interval, n_bars=1000)
            if df is not None and not df.empty:
                df['timeframe'] = label
                return df
            else:
                print(f"⚠️ Empty data for {symbol} [{label}] (Attempt {attempt}/{max_attempts})")
        except (socket.timeout, ssl.SSLError, Exception) as e:
            print(f"⏳ Error for {symbol} [{label}] (Attempt {attempt}/{max_attempts}): {e}")
        
        attempt += 1
        time.sleep(retry_delay)
    
    print(f"❌ Failed to fetch {symbol} [{label}] after {max_attempts} attempts.")
    return None

def fetch_and_save_all(symbol):
    symbol_data = {}

    for label, interval in interval_map.items():
        df = fetch_with_retry(symbol, label, interval)
        if df is not None:
            symbol_data[label] = df

    if len(symbol_data) == len(interval_map):
        # Concatenate and reset index safely
        df_all = pd.concat(symbol_data.values(), keys=symbol_data.keys(), names=['Timeframe', 'Original_Index'])
        df_reset = df_all.reset_index()
        
        filepath = os.path.join(output_dir, f"{symbol}.json")
        df_reset.to_json(filepath, orient='records', date_format='iso', indent=4)
        print(f"✅ Saved: {symbol}")
    else:
        print(f"❌ Skipped {symbol} due to missing timeframes.")

symbols = [
    'NIFTY', 'CNX100', 'CNX200', 'NIFTY_CAPITAL_MKT', 'NIFTYJR',
    'NIFTY_MID_SELECT', 'CNXSMALLCAP', 'CNXMIDCAP', 'BANKNIFTY', 
    'CNXFINANCE'
]

if __name__ == "__main__":
    for symbol in symbols:
        fetch_and_save_all(symbol)
