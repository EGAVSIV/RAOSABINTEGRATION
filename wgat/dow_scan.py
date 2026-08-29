"""
generate_dow_json.py
=====================================================================
Dow Theory + Multi-Level Fibonacci Entry Scanner

Reads OHLC Parquet data from the exact folder structure defined in
the second file, performs swing & Fibonacci calculations, and exports
the results to `resultdow.json`.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd

# =====================================================
# CONFIG & FOLDER MAPPING (Matched to Second File)
# =====================================================
TIMEFRAME_FOLDERS = {
    "15 Min": "stockdata_15",
    "1 Hour": "stockdata_1H",
    "Daily": "stockdata_D",
    "Weekly": "stockdata_W",
    "Monthly": "stockdata_M",
}

FIB_LEVELS = {
    "23%": 0.23,
    "38%": 0.38,
    "50%": 0.50,
    "61.8%": 0.618,
    "78%": 0.78,
}

FIB_RANGES = {
    "23%": (0.21, 0.25),
    "38%": (0.36, 0.40),
    "50%": (0.49, 0.52),
    "61.8%": (0.60, 0.62),
    "78%": (0.76, 0.78),
}

# =====================================================
# JSON ENCODER
# =====================================================
class NpEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if np.isnan(o) else float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (pd.Timestamp, datetime, date)):
            return o.isoformat()
        if isinstance(o, np.ndarray):
            return o.tolist()
        try:
            if pd.isna(o):
                return None
        except (TypeError, ValueError):
            pass
        return super().default(o)

def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, cls=NpEncoder, allow_nan=False)

# =====================================================
# PARQUET DATA LOADERS & HELPERS
# =====================================================
def list_symbols(folder: Path) -> list[str]:
    if not folder.exists():
        return []
    return sorted(f.stem for f in folder.glob("*.parquet") if not f.stem.startswith("_"))

def load_ohlc_parquet(folder: Path, symbol: str) -> pd.DataFrame:
    filepath = folder / f"{symbol}.parquet"
    df = pd.read_parquet(filepath)
    df.index = pd.to_datetime(df.index)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.sort_index()
    return df[~df.index.duplicated(keep="last")]

def filter_until_date(df: pd.DataFrame, until) -> pd.DataFrame:
    until = pd.to_datetime(until)
    return df[df.index <= until].copy()

def latest_date_for_folder(folder: Path):
    if not folder.exists():
        return None
    latest = None
    for f in folder.glob("*.parquet"):
        if f.stem.startswith("_"):
            continue
        try:
            df = pd.read_parquet(f)
            df.index = pd.to_datetime(df.index)
            m = df.index.max()
        except Exception:
            continue
        if latest is None or m > latest:
            latest = m
    return latest

# =====================================================
# DOW THEORY SWING + TREND
# =====================================================
def detect_swings(df: pd.DataFrame, order: int = 3) -> pd.DataFrame:
    high = df["high"].values
    low = df["low"].values

    swing_high = np.zeros(len(df), dtype=bool)
    swing_low = np.zeros(len(df), dtype=bool)

    for i in range(order, len(df) - order):
        if high[i] == max(high[i - order:i + order + 1]):
            swing_high[i] = True
        if low[i] == min(low[i - order:i + order + 1]):
            swing_low[i] = True

    out = df.copy()
    out["swing_high"] = swing_high
    out["swing_low"] = swing_low
    return out

def label_structure(df: pd.DataFrame) -> pd.DataFrame:
    swings = df[(df["swing_high"]) | (df["swing_low"])].copy()
    if swings.empty:
        return swings

    swings["type"] = np.where(swings["swing_high"], "H", "L")
    swings["price"] = np.where(swings["swing_high"], swings["high"], swings["low"])
    swings["label"] = None

    last_H = None
    last_L = None

    for idx in swings.index:
        row = swings.loc[idx]
        if row["type"] == "H":
            if last_H is None:
                swings.at[idx, "label"] = "H"
            else:
                swings.at[idx, "label"] = "HH" if row["price"] > last_H else "LH"
            last_H = row["price"]
        else:
            if last_L is None:
                swings.at[idx, "label"] = "L"
            else:
                swings.at[idx, "label"] = "HL" if row["price"] > last_L else "LL"
            last_L = row["price"]

    return swings

def classify_last_bucket(swings: pd.DataFrame) -> str:
    labels = list(swings["label"].dropna())
    if len(labels) < 4:
        return "Triangle / Sideways"

    last4 = labels[-4:]

    if last4 == ["HH", "HL", "LH", "LL"]:
        return "Reversal To Downtrend"
    if last4 == ["LL", "LH", "HL", "HH"]:
        return "Reversal To Uptrend"

    if all(l in ["HH", "HL"] for l in last4):
        return "Uptrend"

    if all(l in ["LL", "LH"] for l in last4):
        return "Downtrend"

    return "Triangle / Sideways"

# =====================================================
# FIBONACCI RETRACEMENTS
# =====================================================
def fib_levels_up(swings: pd.DataFrame):
    sw = swings.copy()
    last_HL = sw[sw["label"] == "HL"].tail(1)
    last_HH = sw[sw["label"] == "HH"].tail(1)
    if last_HL.empty or last_HH.empty:
        return None

    if last_HL.index[-1] > last_HH.index[-1]:
        return None

    low_price = last_HL["price"].iloc[0]
    high_price = last_HH["price"].iloc[0]
    if high_price == low_price:
        return None

    leg = high_price - low_price
    out = {}
    for name, pct in FIB_LEVELS.items():
        out[name] = high_price - leg * pct
    return out, low_price, high_price

def fib_levels_down(swings: pd.DataFrame):
    sw = swings.copy()
    last_LH = sw[sw["label"] == "LH"].tail(1)
    last_LL = sw[sw["label"] == "LL"].tail(1)
    if last_LH.empty or last_LL.empty:
        return None

    if last_LH.index[-1] > last_LL.index[-1]:
        return None

    high_price = last_LH["price"].iloc[0]
    low_price = last_LL["price"].iloc[0]
    if high_price == low_price:
        return None

    leg = high_price - low_price
    out = {}
    for name, pct in FIB_LEVELS.items():
        out[name] = low_price + leg * pct
    return out, low_price, high_price

def check_fib_entries(df: pd.DataFrame, swings: pd.DataFrame, bucket: str):
    close = df["close"].iloc[-1]

    fib_hits = {
        "23% Bull": False, "38% Bull": False, "50% Bull": False,
        "61.8% Bull": False, "78% Bull": False,
        "23% Bear": False, "38% Bear": False, "50% Bear": False,
        "61.8% Bear": False, "78% Bear": False,
    }
    fib_prices = {f"{k} Up": None for k in FIB_LEVELS.keys()}
    fib_prices.update({f"{k} Down": None for k in FIB_LEVELS.keys()})

    if bucket == "Uptrend":
        res = fib_levels_up(swings)
        if res is None:
            return fib_hits, fib_prices
        prices_dict, low_price, high_price = res

        for name, price in prices_dict.items():
            low_pct, high_pct = FIB_RANGES[name]
            leg = high_price - low_price
            price_low = high_price - leg * high_pct
            price_high = high_price - leg * low_pct
            fib_prices[f"{name} Up"] = float(price)

            if price_low <= close <= price_high:
                fib_hits[f"{name} Bull"] = True

    if bucket == "Downtrend":
        res = fib_levels_down(swings)
        if res is None:
            return fib_hits, fib_prices
        prices_dict, low_price, high_price = res

        for name, price in prices_dict.items():
            low_pct, high_pct = FIB_RANGES[name]
            leg = high_price - low_price
            price_low = low_price + leg * low_pct
            price_high = low_price + leg * high_pct
            fib_prices[f"{name} Down"] = float(price)

            if price_low <= close <= price_high:
                fib_hits[f"{name} Bear"] = True

    return fib_hits, fib_prices

# =====================================================
# TIMEFRAME SCANNER & EXECUTION
# =====================================================
def scan_timeframe(root: Path, timeframe_label: str, scan_date) -> list[dict]:
    folder = root / TIMEFRAME_FOLDERS[timeframe_label]
    symbols = list_symbols(folder)
    results = []

    for symbol in symbols:
        try:
            df = load_ohlc_parquet(folder, symbol)
            df = filter_until_date(df, scan_date)
            if len(df) < 150:
                continue

            df_sw = detect_swings(df, order=3)
            swings = label_structure(df_sw)
            if swings.empty or swings["label"].dropna().shape[0] < 4:
                continue

            bucket = classify_last_bucket(swings)
            fib_hits, fib_prices = check_fib_entries(df, swings, bucket)

            row = {
                "stock": symbol,
                "timeframe": timeframe_label,
                "trend_bucket": bucket,
                "last_close": float(df["close"].iloc[-1]),
                "last_date": df.index[-1].isoformat(),
            }
            row.update({k.lower().replace(" ", "_").replace("%", "pct").replace(".", ""): v
                        for k, v in fib_hits.items()})
            row.update({k.lower().replace(" ", "_").replace("%", "pct").replace(".", ""): v
                        for k, v in fib_prices.items()})
            results.append(row)
        except Exception:
            continue

    return results

def run_full_scan(root: Path, scan_date, timeframes: list[str] | None = None) -> dict:
    timeframes = timeframes or list(TIMEFRAME_FOLDERS.keys())
    all_rows: list[dict] = []
    per_tf_meta = {}

    for tf in timeframes:
        folder = root / TIMEFRAME_FOLDERS[tf]
        latest = latest_date_for_folder(folder)
        rows = scan_timeframe(root, tf, scan_date)
        all_rows.extend(rows)
        per_tf_meta[tf] = {
            "symbol_count": len(list_symbols(folder)),
            "latest_candle": latest.isoformat() if latest is not None else None,
            "matched": len(rows),
        }

    return {
        "scan_type": "dow_theory_fib",
        "scan_date": pd.to_datetime(scan_date).date().isoformat(),
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "timeframes": per_tf_meta,
        "results": all_rows,
    }

# =====================================================
# CLI COMMANDS
# =====================================================
def main():
    ap = argparse.ArgumentParser(description="Dow Theory scanner using Parquet input and JSON output")
    ap.add_argument("--root", default=".", help="Directory containing stockdata_* Parquet folders")
    ap.add_argument("--date", default=None, help="Scan date YYYY-MM-DD")
    ap.add_argument("--timeframes", nargs="*", default=None, help="Specific timeframes to scan")
    ap.add_argument("--out", default="resultdow.json", help="Output JSON path")
    args = ap.parse_args()

    root = Path(args.root).resolve()
    scan_date = pd.to_datetime(args.date) if args.date else pd.Timestamp.today()

    payload = run_full_scan(root, scan_date, args.timeframes)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path
    
    write_json(out_path, payload)
    print(f"✅ Scan Complete! {len(payload['results'])} entries saved to {out_path}")

if __name__ == "__main__":
    main()
