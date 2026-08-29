"""
Dow Theory Trend + Fibonacci Entry Scanner
------------------------------------------
Streamlit-free version of DOW.py.

Input folders (project root):
    stockdata_15
    stockdata_1H
    stockdata_D
    stockdata_W
    stockdata_M

Input files: JSON (one file per symbol).
Output:
    dow_scan_results.json

The calculation logic is kept the same as the original DOW.py.
The scanner automatically uses the latest candle available in each timeframe.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# =====================================================
# CONFIGURATION
# =====================================================
ROOT = Path(__file__).resolve().parent

DATA_FOLDERS = {
    "15 Min": ROOT / "stockdata_15",
    "1 Hour": ROOT / "stockdata_1H",
    "Daily": ROOT / "stockdata_D",
    "Weekly": ROOT / "stockdata_W",
    "Monthly": ROOT / "stockdata_M",
}

OUTPUT_FILE = ROOT / "dow_scan_results.json"
MIN_BARS = 150
SWING_ORDER = 3


# =====================================================
# JSON DATA LOADER
# =====================================================
def _unwrap_json(obj: Any) -> Any:
    """Unwrap common collector JSON envelopes."""
    if isinstance(obj, dict):
        for key in ("data", "candles", "ohlcv", "rows", "records", "values"):
            if key in obj and isinstance(obj[key], (list, dict)):
                return obj[key]
    return obj


def load_json_ohlcv(path: Path) -> pd.DataFrame:
    """Read a symbol JSON file and return a normalized OHLCV DataFrame.

    Supported common JSON layouts:
      1. [{"date": ..., "open": ..., "high": ..., ...}, ...]
      2. {"data": [{...}, ...]}
      3. {"timestamp": [...], "open": [...], "high": [...], ...}
      4. {"2026-08-28": {"open": ..., "high": ..., ...}, ...}

    The date/time column may be named date, datetime, time, timestamp,
    Date, or Datetime. If no explicit time column exists, the DataFrame's
    existing index is used when possible.
    """
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    raw = _unwrap_json(raw)

    if isinstance(raw, list):
        df = pd.DataFrame(raw)
    elif isinstance(raw, dict):
        # Column-oriented JSON: {"timestamp": [...], "open": [...], ...}
        if any(isinstance(v, list) for v in raw.values()):
            df = pd.DataFrame(raw)
        else:
            # Date/datetime keyed JSON.
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

    # Normalize column names.
    df.columns = [str(c).strip().lower() for c in df.columns]

    # Find datetime column.
    datetime_col = next(
        (c for c in ("datetime", "date", "time", "timestamp", "t") if c in df.columns),
        None,
    )

    if datetime_col is not None:
        # Unix timestamps are frequently stored as seconds or milliseconds.
        if pd.api.types.is_numeric_dtype(df[datetime_col]):
            numeric = pd.to_numeric(df[datetime_col], errors="coerce")
            median = numeric.dropna().median() if not numeric.dropna().empty else 0
            unit = "ms" if median > 10_000_000_000 else "s"
            dt = pd.to_datetime(numeric, unit=unit, errors="coerce")
        else:
            dt = pd.to_datetime(df[datetime_col], errors="coerce")
        df = df.loc[dt.notna()].copy()
        df.index = dt[dt.notna()]
    else:
        # Try an existing index only if it is datetime-like.
        try:
            dt = pd.to_datetime(df.index, errors="coerce")
            if pd.Series(dt).notna().all():
                df.index = dt
            else:
                raise ValueError("No datetime column found")
        except Exception as exc:
            raise ValueError(
                f"No date/time field found in {path.name}. Expected date/datetime/time/timestamp."
            ) from exc

    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing OHLC columns: {missing}")

    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df.dropna(subset=required)
    return df


# =====================================================
# DOW THEORY SWING + TREND
# =====================================================
def detect_swings(df: pd.DataFrame, order: int = 3) -> pd.DataFrame:
    high = df["high"].values
    low = df["low"].values

    swing_high = np.zeros(len(df), dtype=bool)
    swing_low = np.zeros(len(df), dtype=bool)

    for i in range(order, len(df) - order):
        if high[i] == max(high[i - order : i + order + 1]):
            swing_high[i] = True
        if low[i] == min(low[i - order : i + order + 1]):
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
# FIBONACCI RETRACEMENTS (SAME LOGIC AS ORIGINAL)
# =====================================================
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
    fib_prices = {f"{k} Up": None for k in FIB_LEVELS}
    fib_prices.update({f"{k} Down": None for k in FIB_LEVELS})

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
# SCANNER
# =====================================================
def scan_timeframe(folder: Path, timeframe: str) -> dict:
    files = sorted(folder.glob("*.json"))
    results = []
    errors = []
    latest_date = None

    if not folder.exists():
        return {
            "timeframe": timeframe,
            "folder": folder.name,
            "scan_date": None,
            "symbols_scanned": 0,
            "results": [],
            "errors": [f"Folder not found: {folder}"],
        }

    for path in files:
        symbol = path.stem
        try:
            df = load_json_ohlcv(path)
            if df.empty:
                continue

            latest_date = df.index.max() if latest_date is None else max(latest_date, df.index.max())
            df = df[df.index <= latest_date].copy()

            if len(df) < MIN_BARS:
                continue

            df_sw = detect_swings(df, order=SWING_ORDER)
            swings = label_structure(df_sw)
            if swings.empty or swings["label"].dropna().shape[0] < 4:
                continue

            bucket = classify_last_bucket(swings)
            fib_hits, fib_prices = check_fib_entries(df, swings, bucket)

            row = {
                "Stock": symbol,
                "Timeframe": timeframe,
                "Trend Bucket": bucket,
                "Scan Date": df.index[-1].isoformat(),
                "Close": float(df["close"].iloc[-1]),
            }
            row.update(fib_hits)
            row.update(fib_prices)
            results.append(row)

        except Exception as exc:
            errors.append({"Stock": symbol, "Error": str(exc)})

    return {
        "timeframe": timeframe,
        "folder": folder.name,
        "scan_date": latest_date.isoformat() if latest_date is not None else None,
        "symbols_scanned": len(files),
        "results_count": len(results),
        "results": results,
        "errors": errors,
    }


def main() -> None:
    output = {
        "scanner": "Dow Theory Trend + Fibonacci Entry Scanner",
        "source_format": "JSON",
        "generated_at": pd.Timestamp.now().isoformat(),
        "data_root": str(ROOT),
        "timeframes": {},
    }

    for timeframe, folder in DATA_FOLDERS.items():
        print(f"Scanning {timeframe}: {folder}")
        output["timeframes"][timeframe] = scan_timeframe(folder, timeframe)

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, allow_nan=False)

    print(f"\nDone. Result JSON written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
