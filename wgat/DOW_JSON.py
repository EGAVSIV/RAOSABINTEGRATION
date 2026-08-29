"""Dow Theory Trend + Fibonacci Entry Scanner.

Streamlit-free JSON scanner.
Script location: ROOT/wgat/DOW_JSON.py
Data location:   ROOT/stockdata_*/
Output location: ROOT/wgat/resultdow.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent

DATA_FOLDERS = {
    "15 Min": ROOT_DIR / "stockdata_15",
    "1 Hour": ROOT_DIR / "stockdata_1H",
    "Daily": ROOT_DIR / "stockdata_D",
    "Weekly": ROOT_DIR / "stockdata_W",
    "Monthly": ROOT_DIR / "stockdata_M",
}

MIN_BARS = 150
SWING_ORDER = 3

FIB_LEVELS = {"23%": 0.23, "38%": 0.38, "50%": 0.50, "61.8%": 0.618, "78%": 0.78}
FIB_RANGES = {"23%": (0.21, 0.25), "38%": (0.36, 0.40), "50%": (0.49, 0.52), "61.8%": (0.60, 0.62), "78%": (0.76, 0.78)}


def _unwrap_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        for key in ("data", "candles", "ohlcv", "rows", "records", "values"):
            if key in obj and isinstance(obj[key], (list, dict)):
                return obj[key]
    return obj


def load_json_ohlcv(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8") as f:
        raw = _unwrap_json(json.load(f))

    if isinstance(raw, list):
        df = pd.DataFrame(raw)
    elif isinstance(raw, dict):
        if any(isinstance(v, list) for v in raw.values()):
            df = pd.DataFrame(raw)
        else:
            rows = []
            for key, value in raw.items():
                if isinstance(value, dict):
                    row = dict(value)
                    row.setdefault("datetime", key)
                    rows.append(row)
            df = pd.DataFrame(rows)
    else:
        raise ValueError(f"Unsupported JSON root type in {path.name}")

    if df.empty:
        return df

    df.columns = [str(c).strip().lower() for c in df.columns]
    dt_col = next((c for c in ("datetime", "date", "time", "timestamp", "t") if c in df.columns), None)

    if dt_col is None:
        raise ValueError(f"No datetime field found in {path.name}")

    if pd.api.types.is_numeric_dtype(df[dt_col]):
        n = pd.to_numeric(df[dt_col], errors="coerce")
        valid = n.dropna()
        unit = "ms" if (not valid.empty and valid.median() > 10_000_000_000) else "s"
        dt = pd.to_datetime(n, unit=unit, errors="coerce", utc=True)
    else:
        dt = pd.to_datetime(df[dt_col], errors="coerce", utc=True)

    mask = dt.notna()
    df = df.loc[mask].copy()
    df.index = dt.loc[mask]

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing OHLC columns: {missing}")

    for c in required + ["volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    return df[~df.index.duplicated(keep="last")].sort_index().dropna(subset=required)


def filter_until_date(df: pd.DataFrame, scan_date: pd.Timestamp) -> pd.DataFrame:
    return df[df.index <= scan_date].copy()


def detect_swings(df: pd.DataFrame, order: int = 3) -> pd.DataFrame:
    high, low = df["high"].values, df["low"].values
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
    last_H = last_L = None
    for idx in swings.index:
        row = swings.loc[idx]
        if row["type"] == "H":
            swings.at[idx, "label"] = "H" if last_H is None else ("HH" if row["price"] > last_H else "LH")
            last_H = row["price"]
        else:
            swings.at[idx, "label"] = "L" if last_L is None else ("HL" if row["price"] > last_L else "LL")
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
    if all(x in ("HH", "HL") for x in last4):
        return "Uptrend"
    if all(x in ("LL", "LH") for x in last4):
        return "Downtrend"
    return "Triangle / Sideways"


def fib_levels_up(swings):
    last_HL = swings[swings["label"] == "HL"].tail(1)
    last_HH = swings[swings["label"] == "HH"].tail(1)
    if last_HL.empty or last_HH.empty or last_HL.index[-1] > last_HH.index[-1]:
        return None
    low_price, high_price = last_HL["price"].iloc[0], last_HH["price"].iloc[0]
    if high_price == low_price:
        return None
    leg = high_price - low_price
    return {k: high_price - leg * p for k, p in FIB_LEVELS.items()}, low_price, high_price


def fib_levels_down(swings):
    last_LH = swings[swings["label"] == "LH"].tail(1)
    last_LL = swings[swings["label"] == "LL"].tail(1)
    if last_LH.empty or last_LL.empty or last_LH.index[-1] > last_LL.index[-1]:
        return None
    high_price, low_price = last_LH["price"].iloc[0], last_LL["price"].iloc[0]
    if high_price == low_price:
        return None
    leg = high_price - low_price
    return {k: low_price + leg * p for k, p in FIB_LEVELS.items()}, low_price, high_price


def check_fib_entries(df, swings, bucket):
    close = df["close"].iloc[-1]
    fib_hits = {f"{k} Bull": False for k in FIB_LEVELS}
    fib_hits.update({f"{k} Bear": False for k in FIB_LEVELS})
    fib_prices = {f"{k} Up": None for k in FIB_LEVELS}
    fib_prices.update({f"{k} Down": None for k in FIB_LEVELS})

    if bucket == "Uptrend":
        res = fib_levels_up(swings)
        if res is None:
            return fib_hits, fib_prices
        prices, low_price, high_price = res
        leg = high_price - low_price
        for name, price in prices.items():
            low_pct, high_pct = FIB_RANGES[name]
            price_low = high_price - leg * high_pct
            price_high = high_price - leg * low_pct
            fib_prices[f"{name} Up"] = float(price)
            if price_low <= close <= price_high:
                fib_hits[f"{name} Bull"] = True

    elif bucket == "Downtrend":
        res = fib_levels_down(swings)
        if res is None:
            return fib_hits, fib_prices
        prices, low_price, high_price = res
        leg = high_price - low_price
        for name, price in prices.items():
            low_pct, high_pct = FIB_RANGES[name]
            price_low = low_price + leg * low_pct
            price_high = low_price + leg * high_pct
            fib_prices[f"{name} Down"] = float(price)
            if price_low <= close <= price_high:
                fib_hits[f"{name} Bear"] = True

    return fib_hits, fib_prices


def scan_timeframe(folder: Path, timeframe: str, scan_date: pd.Timestamp) -> dict:
    files = sorted(folder.glob("*.json")) if folder.exists() else []
    results, errors = [], []
    effective_latest = None

    if not folder.exists():
        return {"timeframe": timeframe, "folder": folder.name, "scan_date": None, "symbols_scanned": 0, "results_count": 0, "results": [], "errors": [f"Folder not found: {folder}"]}

    for path in files:
        try:
            df = filter_until_date(load_json_ohlcv(path), scan_date)
            if df.empty or len(df) < MIN_BARS:
                continue
            effective_latest = df.index[-1] if effective_latest is None else max(effective_latest, df.index[-1])
            df_sw = detect_swings(df, SWING_ORDER)
            swings = label_structure(df_sw)
            if swings.empty or swings["label"].dropna().shape[0] < 4:
                continue
            bucket = classify_last_bucket(swings)
            fib_hits, fib_prices = check_fib_entries(df, swings, bucket)
            row = {
                "Stock": path.stem,
                "Timeframe": timeframe,
                "Trend Bucket": bucket,
                "Scan Date": df.index[-1].isoformat(),
                "Close": float(df["close"].iloc[-1]),
            }
            row.update(fib_hits)
            row.update(fib_prices)
            results.append(row)
        except Exception as exc:
            errors.append({"Stock": path.stem, "Error": str(exc)})

    return {
        "timeframe": timeframe,
        "folder": folder.name,
        "scan_date": effective_latest.isoformat() if effective_latest is not None else scan_date.isoformat(),
        "symbols_scanned": len(files),
        "results_count": len(results),
        "results": results,
        "errors": errors,
    }


def latest_available_date() -> pd.Timestamp:
    latest = None
    folder = DATA_FOLDERS["Daily"]
    for path in folder.glob("*.json") if folder.exists() else []:
        try:
            df = load_json_ohlcv(path)
            if not df.empty:
                latest = df.index.max() if latest is None else max(latest, df.index.max())
        except Exception:
            pass
    if latest is None:
        raise RuntimeError(f"No valid JSON OHLC data found in {folder}")
    return latest


def main():
    parser = argparse.ArgumentParser(description="Dow Theory JSON scanner")
    parser.add_argument("--date", help="Scan as-of date YYYY-MM-DD")
    parser.add_argument("--out", default="resultdow.json", help="Output JSON filename")
    args = parser.parse_args()

    scan_date = pd.Timestamp(args.date, tz="UTC") if args.date else latest_available_date()
    output = {
        "scanner": "Dow Theory Trend + Fibonacci Entry Scanner",
        "source_format": "JSON",
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "data_root": str(ROOT_DIR),
        "scan_date": scan_date.isoformat(),
        "timeframes": {},
    }

    for timeframe, folder in DATA_FOLDERS.items():
        print(f"Scanning {timeframe}: {folder}")
        output["timeframes"][timeframe] = scan_timeframe(folder, timeframe, scan_date)

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = SCRIPT_DIR / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, allow_nan=False)

    print(f"Data root: {ROOT_DIR}")
    print(f"Output: {out_path}")


if __name__ == "__main__":
    main()
