"""
wgat_scan.py
=====================================================================
Wave Going Against The Tide (multi-timeframe MACD alignment) +
Swing/Momentum scan.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, date
from pathlib import Path

import numpy as np
import pandas as pd

TIMEFRAME_FOLDERS = {
    "Daily": "stockdata_D",
    "Weekly": "stockdata_W",
    "Monthly": "stockdata_M",
}

REQUIRED_COLS = ["open", "high", "low", "close"]

FIELD_ALIASES = {
    "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
    "t": "date", "time": "date", "timestamp": "date", "datetime": "date", "dt": "date",
}


def resolve_root(root: str | None) -> Path:
    if root:
        return Path(root).resolve()
    return Path(__file__).resolve().parent.parent


def data_folder(root: Path, timeframe_label: str) -> Path:
    return root / TIMEFRAME_FOLDERS[timeframe_label]


def list_symbols(folder: Path) -> list[str]:
    if not folder.exists():
        return []
    return sorted(f.stem for f in folder.glob("*.json") if not f.stem.startswith("_"))


def load_ohlc_json(folder: Path, symbol: str) -> pd.DataFrame:
    with open(folder / f"{symbol}.json", "r") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        for key in ("data", "records", "rows", "result", "bars", "ohlc", "candles"):
            if key in raw and isinstance(raw[key], (list, dict)):
                raw = raw[key]
                break

    if isinstance(raw, list):
        df = pd.DataFrame(raw)
    elif isinstance(raw, dict):
        df = pd.DataFrame(raw)
    else:
        raise ValueError(f"{symbol}.json: unrecognised JSON shape")

    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns={k: v for k, v in FIELD_ALIASES.items() if k in df.columns})

    date_col = None
    for cand in ("date", "index"):
        if cand in df.columns:
            date_col = cand
            break
    if date_col is not None:
        df = df.set_index(date_col)

    df.index = pd.to_datetime(df.index)

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{symbol}.json: missing columns {missing}")

    for c in REQUIRED_COLS + (["volume"] if "volume" in df.columns else []):
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df


def filter_until_date(df: pd.DataFrame, until) -> pd.DataFrame:
    if until is None:
        return df.copy()
    until_dt = pd.to_datetime(until)
    if until_dt.time() == datetime.min.time():
        until_dt = until_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    filtered = df[df.index <= until_dt].copy()
    return filtered if not filtered.empty else df.copy()


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


def EMA(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def MACD(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = series.ewm(span=fast, adjust=False, min_periods=fast).mean()
    ema_slow = series.ewm(span=slow, adjust=False, min_periods=slow).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def RSI(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.fillna(100)
    return rsi


def ADX(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    plus_dm = pd.Series(plus_dm, index=high.index)
    minus_dm = pd.Series(minus_dm, index=high.index)

    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    atr = tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1 / period, adjust=False, min_periods=period).mean() / atr)

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return adx


def get_macd_trend(series: pd.Series):
    macd, signal, hist = MACD(series, 12, 26, 9)
    macd = macd.dropna()
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


def run_scan(root: Path, scan_date) -> list[dict]:
    folder_d = data_folder(root, "Daily")
    folder_w = data_folder(root, "Weekly")
    folder_m = data_folder(root, "Monthly")

    symbols = list_symbols(folder_d)
    results = []

    for symbol in symbols:
        try:
            # Load Daily Data
            df_d = load_ohlc_json(folder_d, symbol)
            df_d = filter_until_date(df_d, scan_date)
            if len(df_d) < 10:
                continue

            # Fallback resampling for missing timeframe files
            try:
                df_w = load_ohlc_json(folder_w, symbol)
                df_w = filter_until_date(df_w, scan_date)
            except Exception:
                df_w = df_d.resample('W').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()

            try:
                df_m = load_ohlc_json(folder_m, symbol)
                df_m = filter_until_date(df_m, scan_date)
            except Exception:
                df_m = df_d.resample('ME').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()

            d_now, d_prev = get_macd_trend(df_d["close"])
            w_now, _ = get_macd_trend(df_w["close"])
            m_now, _ = get_macd_trend(df_m["close"])

            if not d_now or not w_now or not m_now:
                continue

            trend_status = classify_trend(d_now, d_prev, w_now, m_now)

            df_d = df_d.copy()
            df_d["ema13"] = EMA(df_d["close"], 13)
            df_d["ema50"] = EMA(df_d["close"], 50)
            df_d["ema100"] = EMA(df_d["close"], 100)
            df_d["rsi"] = RSI(df_d["close"], 14)
            df_d["adx"] = ADX(df_d["high"], df_d["low"], df_d["close"], 14)

            latest = df_d.iloc[-1]

            bullish_momentum = bool(
                latest["ema13"] > latest["ema50"] > latest["ema100"]
                and latest["adx"] > 20
                and latest["rsi"] > 55
                and latest["close"] > latest["ema13"]
            )

            bearish_momentum = bool(
                latest["ema13"] < latest["ema50"] < latest["ema100"]
                and latest["adx"] > 20
                and latest["rsi"] < 45
                and latest["close"] < latest["ema13"]
            )

            bullish_swing = bool(latest["ema13"] > latest["ema50"] and latest["rsi"] < 55)
            bearish_swing = bool(latest["ema13"] < latest["ema50"] and latest["rsi"] > 45)

            results.append({
                "stock": symbol,
                "category_1": trend_status,
                "bullish_momentum": bullish_momentum,
                "bearish_momentum": bearish_momentum,
                "bullish_swing": bullish_swing,
                "bearish_swing": bearish_swing,
                "last_close": float(latest["close"]),
                "rsi": None if pd.isna(latest["rsi"]) else round(float(latest["rsi"]), 2),
                "adx": None if pd.isna(latest["adx"]) else round(float(latest["adx"]), 2),
                "ema13": None if pd.isna(latest["ema13"]) else round(float(latest["ema13"]), 2),
                "ema50": None if pd.isna(latest["ema50"]) else round(float(latest["ema50"]), 2),
                "ema100": None if pd.isna(latest["ema100"]) else round(float(latest["ema100"]), 2),
                "last_date": df_d.index[-1].isoformat(),
            })
        except Exception:
            continue

    return results


def main():
    ap = argparse.ArgumentParser(description="WGAT (wave vs tide) scan (single-file, JSON input)")
    ap.add_argument("--root", default=None, help="Folder containing stockdata_* folders")
    ap.add_argument("--date", default=None, help="Scan date YYYY-MM-DD")
    ap.add_argument("--out", default="resultwgat.json", help="Output JSON path")
    args = ap.parse_args()

    root = resolve_root(args.root)
    scan_date = pd.to_datetime(args.date) if args.date else None

    rows = run_scan(root, scan_date)

    payload = {
        "scan_type": "wgat_wave_vs_tide",
        "scan_date": pd.to_datetime(scan_date).date().isoformat() if scan_date else None,
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "symbol_count": len(list_symbols(data_folder(root, "Daily"))),
        "matched": len(rows),
        "results": rows,
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = Path(__file__).resolve().parent / out_path
    write_json(out_path, payload)
    print(f"WGAT scan complete: {len(rows)} rows -> {out_path}")


if __name__ == "__main__":
    main()
