"""
wgat_scan.py
Wave Going Against The Tide (multi-timeframe MACD alignment) + Swing/Momentum
scan. Logic ported from the original WGAT.py Streamlit app. The strategy is
intentionally daily-vs-weekly-vs-monthly ("wave" vs "tide"), so unlike the
Dow scan it always reads stock_data_D / stock_data_W / stock_data_M
regardless of the timeframe list passed on the CLI. talib has been replaced
with the pure-pandas implementations in indicators.py.

Usage:
    python wgat_scan.py --root .. --date 2026-08-28 --out data/wgat_results.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import resolve_root, data_folder, list_symbols, load_df, filter_until_date, write_json
import indicators as ta


def get_macd_trend(series: pd.Series):
    macd, signal, hist = ta.MACD(series, 12, 26, 9)
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
            df_d = load_df(folder_d, symbol)
            df_w = load_df(folder_w, symbol)
            df_m = load_df(folder_m, symbol)

            df_d = filter_until_date(df_d, scan_date)
            df_w = filter_until_date(df_w, scan_date)
            df_m = filter_until_date(df_m, scan_date)

            if len(df_d) < 100:
                continue

            d_now, d_prev = get_macd_trend(df_d["close"])
            w_now, _ = get_macd_trend(df_w["close"])
            m_now, _ = get_macd_trend(df_m["close"])

            if not d_now or not w_now or not m_now:
                continue

            trend_status = classify_trend(d_now, d_prev, w_now, m_now)

            df_d = df_d.copy()
            df_d["ema13"] = ta.EMA(df_d["close"], 13)
            df_d["ema50"] = ta.EMA(df_d["close"], 50)
            df_d["ema100"] = ta.EMA(df_d["close"], 100)
            df_d["rsi"] = ta.RSI(df_d["close"], 14)
            df_d["adx"] = ta.ADX(df_d["high"], df_d["low"], df_d["close"], 14)

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
    ap = argparse.ArgumentParser(description="WGAT (wave vs tide) scan")
    ap.add_argument("--root", default=None, help="Folder containing stock_data_* folders (default: parent of wgat/)")
    ap.add_argument("--date", default=None, help="Scan date YYYY-MM-DD (default: today)")
    ap.add_argument("--out", default="data/wgat_results.json", help="Output JSON path (relative to this script unless absolute)")
    args = ap.parse_args()

    root = resolve_root(args.root)
    scan_date = pd.to_datetime(args.date) if args.date else pd.Timestamp.today()

    rows = run_scan(root, scan_date)

    payload = {
        "scan_type": "wgat_wave_vs_tide",
        "scan_date": pd.to_datetime(scan_date).date().isoformat(),
        "generated_at": pd.Timestamp.now('UTC').isoformat(),
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
