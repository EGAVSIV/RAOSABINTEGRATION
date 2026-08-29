"""
parquet_to_json.py
Converts the raw OHLC parquet files (stock_data_15 / _1H / _D / _W / _M) into
JSON so they can be read by a static HTML dashboard (browsers can't read
.parquet directly). For each timeframe this writes:

    data/raw/<timeframe_folder>/<SYMBOL>.json   -- one file per symbol
    data/raw/<timeframe_folder>/_index.json     -- list of available symbols

Only the last `--bars` candles per symbol are kept by default (500) to keep
the dashboard light; pass --bars 0 for the full history.

Usage:
    python parquet_to_json.py --root .. --timeframes Daily Weekly Monthly --bars 300
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import TIMEFRAME_FOLDERS, resolve_root, data_folder, list_symbols, load_df, write_json


def convert_timeframe(root: Path, timeframe_label: str, out_dir: Path, bars: int):
    folder = data_folder(root, timeframe_label)
    symbols = list_symbols(folder)
    tf_out = out_dir / TIMEFRAME_FOLDERS[timeframe_label]

    converted = []
    for symbol in symbols:
        try:
            df = load_df(folder, symbol)
            if bars and bars > 0:
                df = df.tail(bars)
            has_vol = "volume" in df.columns
            records = []
            for idx, row in df.iterrows():
                vol = None
                if has_vol and pd.notna(row["volume"]):
                    vol = float(row["volume"])
                records.append({
                    "t": idx.isoformat(),
                    "o": round(float(row["open"]), 4),
                    "h": round(float(row["high"]), 4),
                    "l": round(float(row["low"]), 4),
                    "c": round(float(row["close"]), 4),
                    "v": vol,
                })
            write_json(tf_out / f"{symbol}.json", records)
            converted.append(symbol)
        except Exception as e:
            print(f"  skip {symbol}: {e}")
            continue

    write_json(tf_out / "_index.json", {"timeframe": timeframe_label, "symbols": converted})
    return converted


def main():
    ap = argparse.ArgumentParser(description="Convert stock_data_* parquet files to JSON")
    ap.add_argument("--root", default=None)
    ap.add_argument("--timeframes", nargs="*", default=None, help="Subset of timeframes (default: all)")
    ap.add_argument("--bars", type=int, default=500, help="Keep only the last N bars per symbol (0 = all)")
    ap.add_argument("--out", default="data/raw", help="Output folder (relative to this script unless absolute)")
    args = ap.parse_args()

    root = resolve_root(args.root)
    timeframes = args.timeframes or list(TIMEFRAME_FOLDERS.keys())

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = Path(__file__).resolve().parent / out_dir

    for tf in timeframes:
        print(f"Converting {tf} ...")
        converted = convert_timeframe(root, tf, out_dir, args.bars)
        print(f"  {len(converted)} symbols -> {out_dir / TIMEFRAME_FOLDERS[tf]}")


if __name__ == "__main__":
    main()
