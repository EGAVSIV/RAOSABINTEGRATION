"""
Wave Going Against The Tide + SW & MOM Scanner
------------------------------------------------
Streamlit-free version of WGAT.py.

Input folders (project root):
    stockdata_D
    stockdata_W
    stockdata_M

Input files: JSON (one file per symbol).
Output:
    wgat_scan_results.json

The calculation logic is kept the same as the original WGAT.py.
The scanner automatically uses the latest Daily candle and matching
historical Weekly/Monthly data available up to that Daily scan date.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import talib as ta


# =====================================================
# CONFIGURATION
# =====================================================
ROOT = Path(__file__).resolve().parent
DATA_D = ROOT / "stockdata_D"
DATA_W = ROOT / "stockdata_W"
DATA_M = ROOT / "stockdata_M"
OUTPUT_FILE = ROOT / "wgat_scan_results.json"

MIN_DAILY_BARS = 100


# =====================================================
# JSON DATA LOADER
# =====================================================
def _unwrap_json(obj: Any) -> Any:
    if isinstance(obj, dict):
        for key in ("data", "candles", "ohlcv", "rows", "records", "values"):
            if key in obj and isinstance(obj[key], (list, dict)):
                return obj[key]
    return obj


def load_json_ohlcv(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    raw = _unwrap_json(raw)

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

    datetime_col = next(
        (c for c in ("datetime", "date", "time", "timestamp", "t") if c in df.columns),
        None,
    )

    if datetime_col is not None:
        if pd.api.types.is_numeric_dtype(df[datetime_col]):
            numeric = pd.to_numeric(df[datetime_col], errors="coerce")
            valid = numeric.dropna()
            median = valid.median() if not valid.empty else 0
            unit = "ms" if median > 10_000_000_000 else "s"
            dt = pd.to_datetime(numeric, unit=unit, errors="coerce")
        else:
            dt = pd.to_datetime(df[datetime_col], errors="coerce")
        df = df.loc[dt.notna()].copy()
        df.index = dt[dt.notna()]
    else:
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
    return df.dropna(subset=required)


# =====================================================
# SAME CALCULATION LOGIC AS WGAT.py
# =====================================================
def get_macd_trend(series: pd.Series):
    macd, signal, hist = ta.MACD(series, 12, 26, 9)
    macd = pd.Series(macd, index=series.index).dropna()
    if len(macd) < 3:
        return None, None
    now = "Up Tick" if macd.iloc[-1] > macd.iloc[-2] else "Down Tick"
    prev = "Up Tick" if macd.iloc[-2] > macd.iloc[-3] else "Down Tick"
    return now, prev


def classify_trend(d, d1, w, m):
    if d == "Up Tick" and w == "Up Tick" and m == "Up Tick":
        return "Running Uptrend" if d1 == "Up Tick" else "D Aligned Up With W_M"

    if d == "Down Tick" and w == "Down Tick" and m == "Down Tick":
        return "Running Down Trend" if d1 == "Down Tick" else "D Aligned Down With W_M"

    if d == "Down Tick" and w == "Up Tick" and m == "Up Tick":
        return "D (Wave) Going Down/W_M_UP(TIDE)"

    if d == "Up Tick" and w == "Down Tick" and m == "Down Tick":
        return "D(Wave) Going Up /W_M_DN(TIDE)"

    return "No Clear Trend"


def filter_until_date(df: pd.DataFrame, date) -> pd.DataFrame:
    return df[df.index <= date].copy()


# =====================================================
# SCAN ENGINE
# =====================================================
def run_scan(scan_date: pd.Timestamp) -> dict:
    results = []
    errors = []

    if not DATA_D.exists():
        return {
            "scan_date": scan_date.isoformat(),
            "symbols_scanned": 0,
            "results_count": 0,
            "results": [],
            "errors": [f"Folder not found: {DATA_D}"],
        }

    symbols = sorted({f.stem for f in DATA_D.glob("*.json")})

    for symbol in symbols:
        try:
            d_path = DATA_D / f"{symbol}.json"
            w_path = DATA_W / f"{symbol}.json"
            m_path = DATA_M / f"{symbol}.json"

            if not w_path.exists() or not m_path.exists():
                errors.append({
                    "Stock": symbol,
                    "Error": "Weekly or Monthly JSON file missing",
                })
                continue

            df_d = filter_until_date(load_json_ohlcv(d_path), scan_date)
            df_w = filter_until_date(load_json_ohlcv(w_path), scan_date)
            df_m = filter_until_date(load_json_ohlcv(m_path), scan_date)

            if len(df_d) < MIN_DAILY_BARS:
                continue

            # ===== MTF =====
            d_now, d_prev = get_macd_trend(df_d["close"])
            w_now, _ = get_macd_trend(df_w["close"])
            m_now, _ = get_macd_trend(df_m["close"])

            if not d_now or not w_now or not m_now:
                continue

            trend_status = classify_trend(d_now, d_prev, w_now, m_now)

            # ===== DAILY STRUCTURE =====
            df_d = df_d.copy()
            df_d["ema13"] = ta.EMA(df_d["close"], 13)
            df_d["ema50"] = ta.EMA(df_d["close"], 50)
            df_d["ema100"] = ta.EMA(df_d["close"], 100)
            df_d["rsi"] = ta.RSI(df_d["close"], 14)
            df_d["adx"] = ta.ADX(df_d["high"], df_d["low"], df_d["close"], 14)

            latest = df_d.iloc[-1]

            bullish_momentum = (
                latest["ema13"] > latest["ema50"] > latest["ema100"]
                and latest["adx"] > 20
                and latest["rsi"] > 55
                and latest["close"] > latest["ema13"]
            )

            bearish_momentum = (
                latest["ema13"] < latest["ema50"] < latest["ema100"]
                and latest["adx"] > 20
                and latest["rsi"] < 45
                and latest["close"] < latest["ema13"]
            )

            bullish_swing = (
                latest["ema13"] > latest["ema50"]
                and latest["rsi"] < 55
            )

            bearish_swing = (
                latest["ema13"] < latest["ema50"]
                and latest["rsi"] > 45
            )

            results.append({
                "Stock": symbol,
                "Scan Date": df_d.index[-1].isoformat(),
                "Close": float(latest["close"]),
                "Daily MACD": d_now,
                "Previous Daily MACD": d_prev,
                "Weekly MACD": w_now,
                "Monthly MACD": m_now,
                "Category 1": trend_status,
                "Bullish Momentum": bool(bullish_momentum),
                "Bearish Momentum": bool(bearish_momentum),
                "Bullish Swing": bool(bullish_swing),
                "Bearish Swing": bool(bearish_swing),
            })

        except Exception as exc:
            errors.append({"Stock": symbol, "Error": str(exc)})

    return {
        "scan_date": scan_date.isoformat(),
        "symbols_scanned": len(symbols),
        "results_count": len(results),
        "results": results,
        "errors": errors,
    }


def get_latest_daily_date() -> pd.Timestamp:
    latest = None
    for path in DATA_D.glob("*.json"):
        try:
            df = load_json_ohlcv(path)
            if not df.empty:
                value = df.index.max()
                latest = value if latest is None else max(latest, value)
        except Exception:
            continue

    if latest is None:
        raise RuntimeError(f"No valid JSON OHLC data found in {DATA_D}")
    return latest


def main() -> None:
    scan_date = get_latest_daily_date()
    print(f"Latest Daily candle: {scan_date}")
    print("Running WGAT scan...")

    result = run_scan(scan_date)
    output = {
        "scanner": "Wave Going Against The Tide + SW & MOM Scanner",
        "source_format": "JSON",
        "generated_at": pd.Timestamp.now().isoformat(),
        "scan": result,
    }

    with OUTPUT_FILE.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, allow_nan=False)

    print(f"Done. Result JSON written to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
