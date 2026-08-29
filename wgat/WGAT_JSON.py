"""WGAT JSON scanner - Streamlit free, JSON input/output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd

# Script is ROOT/wgat/WGAT_JSON.py, while stockdata_* are in ROOT.
SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
DATA_D = ROOT_DIR / "stockdata_D"
DATA_W = ROOT_DIR / "stockdata_W"
DATA_M = ROOT_DIR / "stockdata_M"


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
        df = pd.DataFrame(raw) if any(isinstance(v, list) for v in raw.values()) else pd.DataFrame([
            {**v, "datetime": v.get("datetime", k)} for k, v in raw.items() if isinstance(v, dict)
        ])
    else:
        raise ValueError(f"Unsupported JSON root type in {path.name}")
    if df.empty:
        return df
    df.columns = [str(c).strip().lower() for c in df.columns]
    dt_col = next((c for c in ("datetime", "date", "time", "timestamp", "t") if c in df.columns), None)
    if dt_col:
        if pd.api.types.is_numeric_dtype(df[dt_col]):
            n = pd.to_numeric(df[dt_col], errors="coerce")
            unit = "ms" if n.dropna().median() > 10_000_000_000 else "s"
            dt = pd.to_datetime(n, unit=unit, errors="coerce", utc=True)
        else:
            dt = pd.to_datetime(df[dt_col], errors="coerce", utc=True)
        mask = dt.notna()
        df = df.loc[mask].copy()
        df.index = dt.loc[mask]
    else:
        raise ValueError(f"No datetime field found in {path.name}")
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing OHLC columns: {missing}")
    for c in required + ["volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[~df.index.duplicated(keep="last")].sort_index().dropna(subset=required)


def ema(s, period):
    return s.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(s, period=14):
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(s):
    fast = ema(s, 12)
    slow = ema(s, 26)
    line = fast - slow
    signal = line.ewm(span=9, adjust=False, min_periods=9).mean()
    return line, signal, line - signal


def true_range(h, l, c):
    pc = c.shift(1)
    return pd.concat([(h-l), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)


def adx(h, l, c, period=14):
    up = h.diff()
    down = -l.diff()
    plus_dm = up.where((up > down) & (up > 0), 0.0)
    minus_dm = down.where((down > up) & (down > 0), 0.0)
    tr = true_range(h, l, c)
    atr = tr.ewm(alpha=1/period, adjust=False, min_periods=period).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1/period, adjust=False, min_periods=period).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1/period, adjust=False, min_periods=period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=1/period, adjust=False, min_periods=period).mean()


def get_macd_trend(series):
    line, _, _ = macd(series)
    line = line.dropna()
    if len(line) < 3:
        return None, None
    now = "Up Tick" if line.iloc[-1] > line.iloc[-2] else "Down Tick"
    prev = "Up Tick" if line.iloc[-2] > line.iloc[-3] else "Down Tick"
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


def run_scan(scan_date):
    results, errors = [], []
    symbols = sorted(p.stem for p in DATA_D.glob("*.json")) if DATA_D.exists() else []
    for symbol in symbols:
        try:
            dp, wp, mp = DATA_D/f"{symbol}.json", DATA_W/f"{symbol}.json", DATA_M/f"{symbol}.json"
            if not wp.exists() or not mp.exists():
                errors.append({"Stock": symbol, "Error": "Weekly or Monthly JSON file missing"})
                continue
            d = load_json_ohlcv(dp); w = load_json_ohlcv(wp); m = load_json_ohlcv(mp)
            d = d[d.index <= scan_date]; w = w[w.index <= scan_date]; m = m[m.index <= scan_date]
            if len(d) < 100:
                continue
            d_now, d_prev = get_macd_trend(d["close"]); w_now, _ = get_macd_trend(w["close"]); m_now, _ = get_macd_trend(m["close"])
            if not all((d_now, w_now, m_now)):
                continue
            dd = d.copy()
            dd["ema13"] = ema(dd.close, 13); dd["ema50"] = ema(dd.close, 50); dd["ema100"] = ema(dd.close, 100)
            dd["rsi"] = rsi(dd.close, 14); dd["adx"] = adx(dd.high, dd.low, dd.close, 14)
            x = dd.iloc[-1]

            # RSI/ADX are written to JSON so the dashboard can display the
            # actual indicator values used by the momentum/swing logic.
            rsi_value = None if pd.isna(x.rsi) else float(x.rsi)
            adx_value = None if pd.isna(x.adx) else float(x.adx)

            results.append({
                "Stock": symbol,
                "Scan Date": x.name.isoformat(),
                "Close": float(x.close),
                "Daily MACD": d_now,
                "Previous Daily MACD": d_prev,
                "Weekly MACD": w_now,
                "Monthly MACD": m_now,
                "Category 1": classify_trend(d_now, d_prev, w_now, m_now),
                "RSI": rsi_value,
                "ADX": adx_value,
                "EMA 13": None if pd.isna(x.ema13) else float(x.ema13),
                "EMA 50": None if pd.isna(x.ema50) else float(x.ema50),
                "EMA 100": None if pd.isna(x.ema100) else float(x.ema100),
                "Bullish Momentum": bool(x.ema13 > x.ema50 > x.ema100 and x.adx > 20 and x.rsi > 55 and x.close > x.ema13),
                "Bearish Momentum": bool(x.ema13 < x.ema50 < x.ema100 and x.adx > 20 and x.rsi < 45 and x.close < x.ema13),
                "Bullish Swing": bool(x.ema13 > x.ema50 and x.rsi < 55),
                "Bearish Swing": bool(x.ema13 < x.ema50 and x.rsi > 45),
            })
        except Exception as exc:
            errors.append({"Stock": symbol, "Error": str(exc)})
    return {"scan_date": scan_date.isoformat(), "symbols_scanned": len(symbols), "results_count": len(results), "results": results, "errors": errors}


def latest_daily_date():
    latest = None
    for p in DATA_D.glob("*.json"):
        try:
            df = load_json_ohlcv(p)
            if not df.empty:
                latest = df.index.max() if latest is None else max(latest, df.index.max())
        except Exception as exc:
            print(f"Skipping {p.name}: {exc}")
    if latest is None:
        raise RuntimeError(f"No valid JSON OHLC data found in {DATA_D}. Expected ROOT/stockdata_D/*.json")
    return latest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Scan date YYYY-MM-DD; defaults to latest Daily candle")
    parser.add_argument("--out", default="resultwgat.json", help="Output filename")
    args = parser.parse_args()
    scan_date = pd.Timestamp(args.date, tz="UTC") if args.date else latest_daily_date()
    result = run_scan(scan_date)
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = SCRIPT_DIR / out_path
    output = {"scanner": "WGAT", "source_format": "JSON", "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "scan": result}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, allow_nan=False)
    print(f"Data root: {ROOT_DIR}")
    print(f"Daily data: {DATA_D}")
    print(f"Scanned symbols: {result['symbols_scanned']}")
    print(f"Results: {result['results_count']}")
    print(f"Output: {out_path}")

if __name__ == "__main__":
    main()
