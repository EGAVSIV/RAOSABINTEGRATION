"""
================================================================================
 GEOTRADER SECTOR — SECTOR ROTATION & RELATIVE STRENGTH ENGINE
================================================================================
Pure-Python / pandas calculation engine. No Streamlit, no plotting library,
no PDF generation. Reads OHLCV JSON from:

    sectorial_index_data/     one file per sector index (incl. the NIFTY
                               benchmark), records mixed across D/W/M
                               timeframes and tagged with a "Timeframe" field
    stockdata_D/               one file per stock, daily candles, used for
                               stock-level RRG and the sector-leader scanner

Computes, anchored to the latest available session (or an explicit
--date for backtesting):

    - Sector vs NIFTY performance table, at several standard lookbacks
    - Multi-timeframe sector rotation (1M / 3M / 6M) + Leading / Improving
      / Lagging / Weakening classification + RS rank
    - RRG-style coordinates: sector-vs-NIFTY, and stock-vs-sector (for
      every sector in sector_stocks.json, not just one — the frontend
      picks which to display)
    - Top strongest sectors
    - Rotation-change alerts (diffs today's classification against the
      previous run's, persisted in state/previous_rotation.json)
    - Sector weight-adjusted "model portfolio"
    - Sector-based top-stock scanner (stocks outperforming their own sector)

...then writes ONE json file: sector/result.json

Usage:
    python engine.py                        # latest date, repo root = ../
    python engine.py --root /path/to/repo
    python engine.py --date 2026-06-15      # backtest anchor date
    python engine.py --out result.json
================================================================================
"""

from __future__ import annotations

import os
import sys
import json
import glob
import argparse
import traceback
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# =====================================================================
# CONFIG
# =====================================================================
BENCHMARK_SYMBOL = "NIFTY"
LOOKBACK_OPTIONS = [10, 15, 20, 30, 45, 60]   # sessions, mirrors the old 10-60 slider
DEFAULT_LOOKBACK = 30
WINDOWS = {"1M": 21, "3M": 63, "6M": 126}      # trading-session windows

DATE_KEYS = ["datetime", "Original_Index", "date", "timestamp", "time", "Date", "Datetime"]
COL_ALIASES = {
    "open":   ["open", "Open", "o", "OPEN"],
    "high":   ["high", "High", "h", "HIGH"],
    "low":    ["low", "Low", "l", "LOW"],
    "close":  ["close", "Close", "c", "CLOSE"],
    "volume": ["volume", "Volume", "v", "vol", "VOLUME"],
}
TF_KEYS = ["Timeframe", "timeframe", "TF", "tf"]


# =====================================================================
# JSON -> DATAFRAME HELPERS  (same conventions as the GeoTrader FNO engine)
# =====================================================================
def _first_present(columns, candidates):
    for c in candidates:
        if c in columns:
            return c
    return None


def _read_json_records(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
        raw = raw["data"]
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        return [raw]
    raise ValueError(f"Unrecognized JSON shape in {path}")


def _records_to_df(records):
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)

    date_col = _first_present(df.columns, DATE_KEYS)
    if date_col is None:
        raise ValueError("No recognizable date/datetime column")
    df["datetime"] = pd.to_datetime(df[date_col], errors="coerce", utc=True)
    df = df.dropna(subset=["datetime"])

    rename_map = {}
    for std, aliases in COL_ALIASES.items():
        col = _first_present(df.columns, aliases)
        if col:
            rename_map[col] = std
    df = df.rename(columns=rename_map)

    for req in ["open", "high", "low", "close"]:
        if req not in df.columns:
            raise ValueError(f"Missing '{req}' column")
        df[req] = pd.to_numeric(df[req], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_values("datetime").drop_duplicates(subset="datetime", keep="last")
    df["date"] = df["datetime"].dt.date
    return df[["date", "open", "high", "low", "close"]].reset_index(drop=True)


def load_flat_symbol_json(path):
    """stockdata_D style: one file, daily candles, flat list of records."""
    return _records_to_df(_read_json_records(path))


def load_daily_from_multi_tf_json(path):
    """sectorial_index_data style: one file, several timeframes mixed
    together and tagged with a 'Timeframe' field — keep the 'D' rows only."""
    records = _read_json_records(path)
    if not records:
        return pd.DataFrame()
    tf_key = _first_present(records[0].keys(), TF_KEYS)
    if tf_key is None:
        return _records_to_df(records)
    daily_records = [
        r for r in records
        if str(r.get(tf_key, "D")).upper().strip() in ("D", "DAY")
    ]
    return _records_to_df(daily_records)


def list_symbols(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.splitext(os.path.basename(p))[0]
                  for p in glob.glob(os.path.join(folder, "*.json")))


# =====================================================================
# RETURN / ROTATION MATH
# =====================================================================
def calc_return(df, bars, anchor_date):
    """% return over `bars` trading sessions, ending on the last session
    at or before anchor_date. None if there isn't enough history."""
    if df is None or df.empty:
        return None
    sub = df[df["date"] <= anchor_date]
    if len(sub) < bars + 1:
        return None
    end_price = sub["close"].iloc[-1]
    start_price = sub["close"].iloc[-(bars + 1)]
    if start_price == 0 or pd.isna(start_price) or pd.isna(end_price):
        return None
    return round(float((end_price / start_price - 1) * 100), 2)


def last_close_on_or_before(df, anchor_date):
    if df is None or df.empty:
        return None
    sub = df[df["date"] <= anchor_date]
    if sub.empty:
        return None
    return sub["date"].iloc[-1]


def classify_rotation(r1m, r3m):
    if r1m is None or r3m is None:
        return "Unknown"
    if r1m > 0 and r3m > 0:
        return "Leading"
    if r1m < 0 and r3m > 0:
        return "Weakening"
    if r1m < 0 and r3m < 0:
        return "Lagging"
    return "Improving"


# =====================================================================
# LOADING
# =====================================================================
def load_sector_universe(sector_dir):
    """Returns {symbol: df} for every *.json in sectorial_index_data,
    daily bars only, including the NIFTY benchmark itself."""
    universe = {}
    for sym in list_symbols(sector_dir):
        try:
            df = load_daily_from_multi_tf_json(os.path.join(sector_dir, f"{sym}.json"))
            if not df.empty:
                universe[sym] = df
        except Exception as e:
            print(f"[sector] skip {sym}: {e}")
    return universe


def load_stock_cache(stock_dir, symbols):
    """Loads only the stocks actually referenced by sector_stocks.json,
    not the whole stockdata_D folder — keeps a full run fast."""
    cache = {}
    for sym in symbols:
        path = os.path.join(stock_dir, f"{sym}.json")
        if not os.path.exists(path):
            continue
        try:
            df = load_flat_symbol_json(path)
            if not df.empty:
                cache[sym] = df
        except Exception as e:
            print(f"[stock] skip {sym}: {e}")
    return cache


def load_sector_stock_map(path):
    if not os.path.exists(path):
        print(f"[sector_stocks] not found at {path} — stock-level panels will be empty")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {k: list(v) for k, v in raw.items()}


# =====================================================================
# STATE (for rotation-change alerts)
# =====================================================================
def load_previous_state(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(path, state):
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# =====================================================================
# MAIN
# =====================================================================
def main():
    parser = argparse.ArgumentParser(description="GeoTrader sector rotation engine")
    parser.add_argument("--root", default=None, help="Repo root containing sectorial_index_data / stockdata_D")
    parser.add_argument("--out", default=None, help="Output json path (default: ./result.json)")
    parser.add_argument("--sector-map", default=None, help="Path to sector_stocks.json")
    parser.add_argument("--state", default=None, help="Path to previous-rotation state json")
    parser.add_argument("--date", default=None, help="Anchor date YYYY-MM-DD for backtesting (default: latest)")
    args = parser.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    root = args.root or os.path.dirname(here)
    out_path = args.out or os.path.join(here, "result.json")
    sector_map_path = args.sector_map or os.path.join(here, "sector_stocks.json")
    state_path = args.state or os.path.join(here, "state", "previous_rotation.json")

    sector_dir = os.path.join(root, "sectorial_index_data")
    stock_dir = os.path.join(root, "stockdata_D")

    print("=" * 78)
    print(f"GeoTrader Sector engine — run started {datetime.now().isoformat()}")
    print(f"  data root : {root}")
    print(f"  output    : {out_path}")
    print("=" * 78)

    sector_universe = load_sector_universe(sector_dir)
    if BENCHMARK_SYMBOL not in sector_universe:
        raise SystemExit(f"❌ Benchmark '{BENCHMARK_SYMBOL}.json' not found in {sector_dir}")

    nifty_df = sector_universe[BENCHMARK_SYMBOL]
    latest_date = nifty_df["date"].iloc[-1]
    anchor_date = pd.to_datetime(args.date).date() if args.date else latest_date

    sector_symbols = sorted(s for s in sector_universe if s != BENCHMARK_SYMBOL)
    print(f"  benchmark : {BENCHMARK_SYMBOL} (latest session {latest_date})")
    print(f"  anchor    : {anchor_date}")
    print(f"  sectors   : {len(sector_symbols)}")

    # ---------------------------------------------------------------
    # 1. Performance table (sector vs NIFTY) at several lookbacks
    # ---------------------------------------------------------------
    nifty_ret_by_lb = {lb: calc_return(nifty_df, lb, anchor_date) for lb in LOOKBACK_OPTIONS}
    performance_table = {}
    for lb in LOOKBACK_OPTIONS:
        nifty_ret = nifty_ret_by_lb[lb]
        rows = []
        for sym in sector_symbols:
            r = calc_return(sector_universe[sym], lb, anchor_date)
            if r is None or nifty_ret is None:
                continue
            rows.append({
                "symbol": sym,
                "return": r,
                "nifty_return": nifty_ret,
                "status": "Outperforming" if r > nifty_ret else "Underperforming",
            })
        rows.sort(key=lambda r: r["return"], reverse=True)
        performance_table[str(lb)] = rows

    # ---------------------------------------------------------------
    # 2. Multi-timeframe rotation table + RRG coordinates
    # ---------------------------------------------------------------
    nifty_1m = calc_return(nifty_df, WINDOWS["1M"], anchor_date)
    rotation_rows = []
    for sym in sector_symbols:
        df = sector_universe[sym]
        r1m = calc_return(df, WINDOWS["1M"], anchor_date)
        r3m = calc_return(df, WINDOWS["3M"], anchor_date)
        r6m = calc_return(df, WINDOWS["6M"], anchor_date)
        if r1m is None or r3m is None:
            continue
        rotation_rows.append({
            "sector": sym,
            "r1m": r1m,
            "r3m": r3m,
            "r6m": r6m,
            "rotation": classify_rotation(r1m, r3m),
            "rs_vs_nifty": round(r1m - nifty_1m, 2) if nifty_1m is not None else None,
            "momentum": round(r1m - r3m, 2),
        })

    rotation_rows.sort(key=lambda r: r["r1m"], reverse=True)
    for i, r in enumerate(rotation_rows, start=1):
        r["rs_rank"] = i

    top_sectors = rotation_rows[:5]

    # ---------------------------------------------------------------
    # 3. Rotation-change alerts (persisted state diff)
    # ---------------------------------------------------------------
    prev_state = load_previous_state(state_path)
    alerts = []
    for r in rotation_rows:
        old = prev_state.get(r["sector"])
        if old and old != r["rotation"]:
            alerts.append({"sector": r["sector"], "from": old, "to": r["rotation"]})
    new_state = {r["sector"]: r["rotation"] for r in rotation_rows}
    save_state(state_path, new_state)

    # ---------------------------------------------------------------
    # 4. Sector weight-adjusted model portfolio
    # ---------------------------------------------------------------
    model_rows = [r for r in rotation_rows if r["rotation"] in ("Leading", "Improving")]
    if model_rows:
        max_rank = max(r["rs_rank"] for r in model_rows)
        raw_weights = [(r, max_rank - r["rs_rank"] + 1) for r in model_rows]
        total_weight = sum(w for _, w in raw_weights) or 1
        model_portfolio = [
            {
                "sector": r["sector"],
                "rotation": r["rotation"],
                "rs_rank": r["rs_rank"],
                "weight_pct": round((w / total_weight) * 100, 2),
            }
            for r, w in sorted(raw_weights, key=lambda t: t[0]["rs_rank"])
        ]
    else:
        model_portfolio = []

    # ---------------------------------------------------------------
    # 5. Stock-level data: RRG per sector + sector-leader scanner
    # ---------------------------------------------------------------
    sector_stock_map = load_sector_stock_map(sector_map_path)
    all_needed_stocks = sorted({s for stocks in sector_stock_map.values() for s in stocks})
    stock_cache = load_stock_cache(stock_dir, all_needed_stocks)
    print(f"  stocks    : {len(stock_cache)}/{len(all_needed_stocks)} referenced symbols loaded")

    rotation_by_sector = {r["sector"]: r for r in rotation_rows}

    stock_rrg = {}
    scanner_rows = []
    model_sector_names = {r["sector"] for r in model_rows}

    for sector, stocks in sector_stock_map.items():
        sec_row = rotation_by_sector.get(sector)
        if sec_row is None:
            continue
        sec_1m = sec_row["r1m"]

        rrg_points = []
        as_of_dates = []
        for sym in stocks:
            sdf = stock_cache.get(sym)
            if sdf is None:
                continue
            r1 = calc_return(sdf, WINDOWS["1M"], anchor_date)
            r3 = calc_return(sdf, WINDOWS["3M"], anchor_date)
            if r1 is None or r3 is None:
                continue
            rrg_points.append({
                "symbol": sym,
                "rs_vs_sector": round(r1 - sec_1m, 2),
                "momentum": round(r1 - r3, 2),
                "r1m": r1,
            })
            d = last_close_on_or_before(sdf, anchor_date)
            if d:
                as_of_dates.append(d)

            if sector in model_sector_names and r1 > sec_1m:
                scanner_rows.append({
                    "sector": sector,
                    "stock": sym,
                    "stock_1m": r1,
                    "sector_1m": sec_1m,
                    "signal": "Sector Leader",
                })

        if rrg_points:
            stock_rrg[sector] = {
                "points": rrg_points,
                "as_of": max(as_of_dates).isoformat() if as_of_dates else None,
                "sector_1m": sec_1m,
            }

    scanner_rows.sort(key=lambda r: r["stock_1m"] - r["sector_1m"], reverse=True)

    # ---------------------------------------------------------------
    # WRITE RESULT
    # ---------------------------------------------------------------
    result = {
        "generated_at": datetime.now().isoformat(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "benchmark": BENCHMARK_SYMBOL,
            "latest_date": latest_date.isoformat(),
            "anchor_date": anchor_date.isoformat() if hasattr(anchor_date, "isoformat") else str(anchor_date),
            "sector_count": len(rotation_rows),
            "lookback_options": LOOKBACK_OPTIONS,
            "default_lookback": DEFAULT_LOOKBACK,
            "sector_map_loaded": bool(sector_stock_map),
            "stocks_loaded": len(stock_cache),
        },
        "nifty_returns": nifty_ret_by_lb,
        "performance_table": performance_table,
        "rotation_table": rotation_rows,
        "top_sectors": top_sectors,
        "rotation_alerts": alerts,
        "model_portfolio": model_portfolio,
        "stock_rrg": stock_rrg,
        "sector_scanner": scanner_rows,
    }

    out_dir = os.path.dirname(out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"\n✅ wrote {out_path}")
    print(f"   Sectors: {len(rotation_rows)} | Alerts: {len(alerts)} | "
          f"Model portfolio: {len(model_portfolio)} | Scanner hits: {len(scanner_rows)} | "
          f"Stock-RRG sectors: {len(stock_rrg)}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
