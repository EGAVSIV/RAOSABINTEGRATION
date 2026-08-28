import pandas as pd
from tvDatafeed import TvDatafeed, Interval
from datetime import datetime
import socket, ssl, time, os

# === TV Datafeed Login ===
username = "EGAVSIV"
password = "Eric$1234"
tv = TvDatafeed(username, password)

# === Only Required Timeframes ===
interval_map = {
    'D': Interval.in_daily,
    'W': Interval.in_weekly,
    'M': Interval.in_monthly
}

# === Output Folder ===
output_dir = "Broad_index_data"
os.makedirs(output_dir, exist_ok=True)

# === Delay for retries ===
retry_delay = 3  # seconds

# === Fetch with infinite retry ===
def fetch_with_retry(symbol, label, interval):
    attempt = 1
    while True:
        try:
            df = tv.get_hist(symbol=symbol, exchange='NSE', interval=interval, n_bars=1000)
            if df is not None and not df.empty:
                df['timeframe'] = label
                return df
            else:
                print(f"⚠️ Empty data for {symbol} [{label}] (Attempt {attempt})")
        except (socket.timeout, ssl.SSLError):
            print(f"⏳ Timeout for {symbol} [{label}] (Attempt {attempt})")
        attempt += 1
        time.sleep(retry_delay)

# === Fetch and Save for One Symbol ===
def fetch_and_save_all(symbol):
    symbol_data = {}

    for label, interval in interval_map.items():
        df = fetch_with_retry(symbol, label, interval)
        if df is not None:
            symbol_data[label] = df

    if len(symbol_data) == len(interval_map):  # All timeframes received
        df_all = pd.concat(symbol_data.values(), keys=symbol_data.keys(), names=['Timeframe'])
        
        # Reset the index so time and timeframe become standard JSON fields
        df_reset = df_all.reset_index()
        
        filepath = os.path.join(output_dir, f"{symbol}.json")
        
        # Export to JSON format
        df_reset.to_json(filepath, orient='records', date_format='iso', indent=4)
        print(f"✅ Saved: {symbol}")
    else:
        print(f"❌ Skipped {symbol} due to missing data.")

# === Symbols List ===
symbols = [
    'NIFTY','CNX100','CNX200','NIFTY_CAPITAL_MKT','NIFTYJR',
    'NIFTY_MID_SELECT','CNXSMALLCAP','CNXMIDCAP','BANKNIFTY', 
    'CNXFINANCE', 'MCXBULLDEX']

# === Run for All Symbols ===
for symbol in symbols:
    fetch_and_save_all(symbol)
