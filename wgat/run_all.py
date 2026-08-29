"""
run_all.py
One command to refresh everything the dashboard reads:
  1. (optional) convert stock_data_* parquet -> data/raw/*.json for chart previews
  2. run the Dow Theory + Fib scan across all 5 timeframes -> data/dow_results.json
  3. run the WGAT wave-vs-tide scan (D/W/M) -> data/wgat_results.json

Usage:
    python run_all.py --root .. --date 2026-08-28
    python run_all.py --root .. --date 2026-08-28 --skip-raw
    python run_all.py --root .. --date 2026-08-28 --raw-timeframes Daily Weekly Monthly --raw-bars 300
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import resolve_root, write_json
import dow_scan
import wgat_scan
import parquet_to_json


def main():
    ap = argparse.ArgumentParser(description="Run Dow + WGAT scans and refresh dashboard data")
    ap.add_argument("--root", default=None, help="Folder containing stock_data_* folders (default: parent of wgat/)")
    ap.add_argument("--date", default=None, help="Scan date YYYY-MM-DD (default: today)")
    ap.add_argument("--skip-raw", action="store_true", help="Skip parquet->JSON OHLC conversion")
    ap.add_argument("--raw-timeframes", nargs="*", default=None, help="Subset of timeframes to convert to raw JSON")
    ap.add_argument("--raw-bars", type=int, default=300, help="Bars per symbol kept in raw JSON (0 = all)")
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    root = resolve_root(args.root)
    scan_date = pd.to_datetime(args.date) if args.date else pd.Timestamp.today()

    print(f"Data root : {root}")
    print(f"Scan date : {scan_date.date()}")
    print("-" * 50)

    if not args.skip_raw:
        print("[1/3] Converting parquet -> JSON (raw OHLC for charts) ...")
        for tf in (args.raw_timeframes or list(dow_scan.TIMEFRAME_FOLDERS.keys())):
            converted = parquet_to_json.convert_timeframe(root, tf, here / "data" / "raw", args.raw_bars)
            print(f"      {tf:10s}: {len(converted)} symbols")
    else:
        print("[1/3] Skipped raw conversion")

    print("[2/3] Running Dow Theory + Fib scan across all timeframes ...")
    dow_payload = dow_scan.run_full_scan(root, scan_date)
    write_json(here / "data" / "dow_results.json", dow_payload)
    print(f"      {len(dow_payload['results'])} rows -> data/dow_results.json")

    print("[3/3] Running WGAT (wave vs tide) scan ...")
    wgat_rows = wgat_scan.run_scan(root, scan_date)
    wgat_payload = {
        "scan_type": "wgat_wave_vs_tide",
        "scan_date": pd.to_datetime(scan_date).date().isoformat(),
        "generated_at": pd.Timestamp.now('UTC').isoformat(),
        "symbol_count": len(dow_scan.list_symbols(dow_scan.data_folder(root, "Daily"))),
        "matched": len(wgat_rows),
        "results": wgat_rows,
    }
    write_json(here / "data" / "wgat_results.json", wgat_payload)
    print(f"      {len(wgat_rows)} rows -> data/wgat_results.json")

    # small manifest the dashboard can poll to know when data last refreshed
    write_json(here / "data" / "manifest.json", {
        "scan_date": pd.to_datetime(scan_date).date().isoformat(),
        "generated_at": pd.Timestamp.now('UTC').isoformat(),
        "dow_rows": len(dow_payload["results"]),
        "wgat_rows": len(wgat_rows),
    })

    print("-" * 50)
    print("Done. Open index.html (via a local server) to view the dashboard.")


if __name__ == "__main__":
    main()
