"""
================================================================================
 GEOTRADER  —  MARKET INTELLIGENCE ENGINE
================================================================================
Pure-Python / pandas calculation engine. No Streamlit, no UI code.

Reads raw OHLCV JSON from the repo's data folders:

    Broad_index_data/        one file per broad market index
                              (records tagged with a "Timeframe" field: D / W / M)
    sectorial_index_data/    one file per sector index (same mixed-timeframe shape)
    stockdata_15/            one file per FNO stock, 15-minute candles
    stockdata_1H/            one file per FNO stock, 1-hour candles
    stockdata_D/             one file per FNO stock, daily candles
    stockdata_W/             one file per FNO stock, weekly candles
    stockdata_M/             one file per FNO stock, monthly candles

Computes RSI(14), Bollinger Bands(20,2), CPR + Camarilla pivots, % change,
advance/decline, sector performance, sector -> stock leaderboards, momentum
streaks, a multi-timeframe RSI scanner and an intraday first-break signal
scan — then writes ONE json file: geotrader/output/result.json

Usage:
    python engine.py                  # uses ../ as the data root (repo root)
    python engine.py --root /path     # explicit repo root
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
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

# =====================================================================
# CONFIG
# =====================================================================
RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2
MOMENTUM_MAX_DAYS = 10
MOMENTUM_MIN_STREAK = 2
INTRADAY_LOOKBACK_DAYS = 7
INTRADAY_TFS = ["15m", "1H"]

TF_LABELS = {"15m": "15 MIN", "1H": "60 MIN", "D": "DAY", "W": "WEEK", "M": "MONTH"}

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
# LOW-LEVEL JSON -> DATAFRAME HELPERS
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
    """Turn a list of OHLCV dict records into a clean, sorted, indexed DataFrame."""
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
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    else:
        df["volume"] = 0.0

    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_values("datetime").drop_duplicates(subset="datetime", keep="last")
    df = df.set_index("datetime")
    return df[["open", "high", "low", "close", "volume"]]


def load_flat_symbol_json(path):
    """stockdata_* style: one file, one timeframe, flat list of OHLCV records."""
    return _records_to_df(_read_json_records(path))


def load_multi_tf_index_json(path):
    """Broad_index_data / sectorial_index_data style: one file holding several
    timeframes at once, disambiguated by a 'Timeframe' field on each record.
    Returns {tf: DataFrame}.
    """
    records = _read_json_records(path)
    if not records:
        return {}

    tf_key = _first_present(records[0].keys(), TF_KEYS)
    if tf_key is None:
        # No timeframe tag -> treat the whole file as a single (daily) series
        return {"D": _records_to_df(records)}

    buckets: dict[str, list] = {}
    for r in records:
        tf_raw = str(r.get(tf_key, "D")).upper().strip()
        tf = {"D": "D", "DAY": "D", "W": "W", "WEEK": "W", "M": "M", "MONTH": "M"}.get(tf_raw, tf_raw)
        buckets.setdefault(tf, []).append(r)

    return {tf: _records_to_df(recs) for tf, recs in buckets.items()}


def list_symbols(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.splitext(os.path.basename(p))[0]
                  for p in glob.glob(os.path.join(folder, "*.json")))


# =====================================================================
# INDICATORS
# =====================================================================
def compute_rsi(close, period=RSI_PERIOD):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.where(avg_loss != 0, 100.0)


def compute_bollinger(close, period=BB_PERIOD, num_std=BB_STD):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    return mid + num_std * std, mid, mid - num_std * std


def compute_pivots(df):
    """Classic CPR (Central Pivot Range) + Camarilla, from the PREVIOUS bar."""
    ph, pl, pc = df["high"].shift(1), df["low"].shift(1), df["close"].shift(1)
    pivot = (ph + pl + pc) / 3
    bc = (ph + pl) / 2
    tc = (pivot - bc) + pivot
    rng = ph - pl
    return (
        pivot, tc, bc,
        pc + rng * 1.1 / 4, pc + rng * 1.1 / 2,   # cam_h3, cam_h4
        pc - rng * 1.1 / 4, pc - rng * 1.1 / 2,   # cam_l3, cam_l4
    )


def enrich(df):
    if df is None or df.empty:
        return df
    df = df.copy()
    df["rsi_14"] = compute_rsi(df["close"])
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = compute_bollinger(df["close"])
    (df["cpr_pivot"], df["cpr_tc"], df["cpr_bc"],
     df["cam_h3"], df["cam_h4"], df["cam_l3"], df["cam_l4"]) = compute_pivots(df)
    return df


# =====================================================================
# SYMBOL -> SECTOR MAP
# =====================================================================
def load_symbol_sector_map(path):
    """Accepts [{"Stocks": "TCS", "Sectors": ["CNXIT", ...]}, ...] (list form)
    or {"TCS": ["CNXIT", ...]} / {"TCS": "CNXIT"} (dict form)."""
    if not os.path.exists(path):
        print(f"[symbol map] not found at {path} — sector leaderboards will be empty")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    out: dict[str, list[str]] = {}
    if isinstance(raw, list):
        for row in raw:
            stock = row.get("Stocks") or row.get("Stock") or row.get("symbol")
            sectors = row.get("Sectors") or row.get("Sector") or []
            if isinstance(sectors, str):
                sectors = [s.strip() for s in sectors.split(",")]
            if stock:
                out[str(stock).strip()] = [str(s).strip() for s in sectors if s]
    elif isinstance(raw, dict):
        for stock, sectors in raw.items():
            if isinstance(sectors, str):
                sectors = [sectors]
            out[str(stock).strip()] = [str(s).strip() for s in sectors]

    print(f"[symbol map] loaded {len(out)} stocks from {path}")
    return out


# =====================================================================
# DATA LOADING
# =====================================================================
def load_universe(root):
    """Returns:
        stock_data[tf][symbol]  -> enriched df   (FNO tradable universe)
        broad_data[tf][symbol]  -> enriched df   (broad market indices)
        sector_data[tf][symbol] -> enriched df   (sector indices)
    """
    stock_dirs = {
        "15m": os.path.join(root, "stockdata_15"),
        "1H":  os.path.join(root, "stockdata_1H"),
        "D":   os.path.join(root, "stockdata_D"),
        "W":   os.path.join(root, "stockdata_W"),
        "M":   os.path.join(root, "stockdata_M"),
    }
    broad_dir = os.path.join(root, "Broad_index_data")
    sector_dir = os.path.join(root, "sectorial_index_data")

    stock_data = {tf: {} for tf in stock_dirs}
    for tf, folder in stock_dirs.items():
        for sym in list_symbols(folder):
            try:
                df = load_flat_symbol_json(os.path.join(folder, f"{sym}.json"))
                if not df.empty:
                    stock_data[tf][sym] = enrich(df)
            except Exception as e:
                print(f"[stock:{tf}] skip {sym}: {e}")

    def load_index_folder(folder, label):
        out = {"D": {}, "W": {}, "M": {}}
        for sym in list_symbols(folder):
            try:
                per_tf = load_multi_tf_index_json(os.path.join(folder, f"{sym}.json"))
                for tf, df in per_tf.items():
                    if tf in out and not df.empty:
                        out[tf][sym] = enrich(df)
            except Exception as e:
                print(f"[{label}] skip {sym}: {e}")
        return out

    broad_data = load_index_folder(broad_dir, "broad")
    sector_data = load_index_folder(sector_dir, "sector")

    return stock_data, broad_data, sector_data


# =====================================================================
# CORE CALCULATIONS
# =====================================================================
def pct_change_last_two(df):
    if df is None or len(df) < 2:
        return 0.0
    p, c = df["close"].iloc[-2], df["close"].iloc[-1]
    if pd.isna(p) or pd.isna(c) or p == 0:
        return 0.0
    return round(((c - p) / p) * 100, 2)


def build_change_table(daily_dict, symbols=None):
    symbols = symbols if symbols is not None else list(daily_dict.keys())
    rows = []
    for sym in symbols:
        df = daily_dict.get(sym)
        if df is None:
            continue
        rows.append({
            "symbol": sym,
            "change": pct_change_last_two(df),
            "close": None if df.empty else round(float(df["close"].iloc[-1]), 2),
        })
    return rows


def closing_streak(df, direction, max_days=MOMENTUM_MAX_DAYS):
    if df is None or len(df) < 2:
        return 0
    closes = df["close"].tail(max_days).values
    streak = 0
    for i in range(len(closes) - 1, 0, -1):
        if direction == "up" and closes[i] > closes[i - 1]:
            streak += 1
        elif direction == "down" and closes[i] < closes[i - 1]:
            streak += 1
        else:
            break
    return streak


def rsi_state(curr, prev):
    if pd.isna(curr) or pd.isna(prev):
        return "NEUTRAL"
    if curr > 60 and prev <= 60:
        return "CHANGE_NOW"
    if curr < 40 and prev >= 40:
        return "CHANGE_NOW"
    if curr > 60:
        return "BULLISH"
    if curr < 40:
        return "BEARISH"
    return "NEUTRAL"


def run_rsi_scanner(stock_data):
    rows = []
    for tf, label in TF_LABELS.items():
        for symbol, df in stock_data.get(tf, {}).items():
            if df is None or len(df) < 2 or "rsi_14" not in df.columns:
                continue
            curr, prev = df["rsi_14"].iloc[-1], df["rsi_14"].iloc[-2]
            if pd.isna(curr) or pd.isna(prev):
                continue
            rows.append({
                "symbol": symbol, "tf": label,
                "rsi": round(float(curr), 2),
                "state": rsi_state(curr, prev),
            })
    return rows


def get_daily_levels(daily_df):
    prev = daily_df.iloc[-2]
    return {
        "day_high": prev["high"], "day_low": prev["low"],
        "cpr_tc": prev.get("cpr_tc"), "cpr_bc": prev.get("cpr_bc"),
        "cam_h4": prev.get("cam_h4"), "cam_l4": prev.get("cam_l4"),
    }


def evaluate_first_break_intraday(symbol, tf, df_tf, daily_df, weekly_df):
    if df_tf is None or len(df_tf) < 2 or "rsi_14" not in df_tf.columns:
        return None
    if daily_df is None or len(daily_df) < 2 or weekly_df is None or len(weekly_df) < 2:
        return None

    daily = get_daily_levels(daily_df)
    prev_week = weekly_df.iloc[-2]
    today = df_tf.index[-1].date()

    for i in range(1, len(df_tf)):
        prev, curr = df_tf.iloc[i - 1], df_tf.iloc[i]
        ts = df_tf.index[i]
        if ts.date() != today:
            continue

        prev_close, curr_close = prev["close"], curr["close"]
        reasons, bull, bear, primary = [], 0, 0, False

        if prev_close < daily["day_high"] and curr_close > daily["day_high"]:
            bull += 1; primary = True; reasons.append(f"Daily High BO @ {ts.strftime('%H:%M')}")
        elif prev_close > daily["day_low"] and curr_close < daily["day_low"]:
            bear += 1; primary = True; reasons.append(f"Daily Low BD @ {ts.strftime('%H:%M')}")
        elif prev_close < prev_week["high"] and curr_close > prev_week["high"]:
            bull += 1; primary = True; reasons.append(f"Weekly High BO @ {ts.strftime('%H:%M')}")
        elif prev_close > prev_week["low"] and curr_close < prev_week["low"]:
            bear += 1; primary = True; reasons.append(f"Weekly Low BD @ {ts.strftime('%H:%M')}")

        if not primary:
            continue

        rsi_prev, rsi_curr = prev["rsi_14"], curr["rsi_14"]
        if pd.notna(rsi_prev) and pd.notna(rsi_curr):
            if rsi_prev < 60 and rsi_curr > 60:
                bull += 1; reasons.append(f"RSI > 60 @ {ts.strftime('%H:%M')}")
            if rsi_prev > 40 and rsi_curr < 40:
                bear += 1; reasons.append(f"RSI < 40 @ {ts.strftime('%H:%M')}")

        if pd.notna(prev.get("bb_upper")) and pd.notna(curr.get("bb_upper")):
            if prev_close < prev["bb_upper"] and curr_close > curr["bb_upper"]:
                bull += 1; reasons.append(f"BB Upper BO @ {ts.strftime('%H:%M')}")
        if pd.notna(prev.get("bb_lower")) and pd.notna(curr.get("bb_lower")):
            if prev_close > prev["bb_lower"] and curr_close < curr["bb_lower"]:
                bear += 1; reasons.append(f"BB Lower BD @ {ts.strftime('%H:%M')}")

        if pd.notna(daily["cpr_tc"]) and prev_close < daily["cpr_tc"] and curr_close > daily["cpr_tc"]:
            bull += 1; reasons.append(f"CPR TC BO @ {ts.strftime('%H:%M')}")
        if pd.notna(daily["cpr_bc"]) and prev_close > daily["cpr_bc"] and curr_close < daily["cpr_bc"]:
            bear += 1; reasons.append(f"CPR BC BD @ {ts.strftime('%H:%M')}")

        if pd.notna(daily["cam_h4"]) and prev_close < daily["cam_h4"] and curr_close > daily["cam_h4"]:
            bull += 1; reasons.append(f"Cam H4 BO @ {ts.strftime('%H:%M')}")
        if pd.notna(daily["cam_l4"]) and prev_close > daily["cam_l4"] and curr_close < daily["cam_l4"]:
            bear += 1; reasons.append(f"Cam L4 BD @ {ts.strftime('%H:%M')}")

        if bull >= 2 and bull > bear:
            return {"symbol": symbol, "tf": tf, "signal": "BUY", "ts": ts.isoformat(), "reasons": reasons}
        if bear >= 2 and bear > bull:
            return {"symbol": symbol, "tf": tf, "signal": "SELL", "ts": ts.isoformat(), "reasons": reasons}
        break

    return None


def run_intraday_scan(stock_data, symbols):
    events = []
    daily_data = stock_data.get("D", {})
    for symbol in symbols:
        daily_df = daily_data.get(symbol)
        if daily_df is None or len(daily_df) < 2:
            continue
        weekly_df = stock_data.get("W", {}).get(symbol)
        if weekly_df is None or len(weekly_df) < 2:
            weekly_df = daily_df.resample("W-FRI").agg({"high": "max", "low": "min"}).dropna()
        for tf in INTRADAY_TFS:
            df_tf = stock_data.get(tf, {}).get(symbol)
            ev = evaluate_first_break_intraday(symbol, tf, df_tf, daily_df, weekly_df)
            if ev:
                events.append(ev)

    cutoff = pd.Timestamp.now(tz="UTC") - timedelta(days=INTRADAY_LOOKBACK_DAYS)
    events = [ev for ev in events if pd.to_datetime(ev["ts"], utc=True) >= cutoff]
    events.sort(key=lambda x: x["ts"], reverse=True)
    return events


# =====================================================================
# MAIN
# =====================================================================
def main():
    parser = argparse.ArgumentParser(description="GeoTrader calculation engine")
    parser.add_argument("--root", default=None,
                         help="Repo root containing the data folders (default: parent of this file's folder)")
    parser.add_argument("--out", default=None, help="Output json path (default: ./output/result.json)")
    parser.add_argument("--symbol-map", default=None, help="Path to symbol_map.json")
    args = parser.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    root = args.root or os.path.dirname(here)
    out_path = args.out or os.path.join(here, "output", "result.json")
    symbol_map_path = args.symbol_map or os.path.join(here, "symbol_map.json")

    print("=" * 78)
    print(f"GeoTrader engine — run started {datetime.now().isoformat()}")
    print(f"  data root : {root}")
    print(f"  output    : {out_path}")
    print("=" * 78)

    stock_data, broad_data, sector_data = load_universe(root)
    sector_map = load_symbol_sector_map(symbol_map_path)

    fno_symbols = sorted(stock_data["D"].keys())
    if not fno_symbols:
        raise SystemExit(f"No daily FNO stock data found under {root}/stockdata_D")

    # ---- Broad market & sector index performance ----
    broader_market = build_change_table(broad_data.get("D", {}))
    sector_performance = build_change_table(sector_data.get("D", {}))

    # ---- FNO universe % change / gainers-losers / advance-decline ----
    fno_change = build_change_table(stock_data["D"], fno_symbols)
    fno_sorted_desc = sorted(fno_change, key=lambda r: r["change"], reverse=True)
    fno_sorted_asc = sorted(fno_change, key=lambda r: r["change"])
    top5, bottom5 = fno_sorted_desc[:5], fno_sorted_asc[:5]

    adv = sum(1 for r in fno_change if r["change"] > 0)
    dec = sum(1 for r in fno_change if r["change"] < 0)
    unch = sum(1 for r in fno_change if r["change"] == 0)

    # ---- Sector -> stock leaderboards ----
    all_sectors = sorted({s for sectors in sector_map.values() for s in sectors})
    sector_stocks = {}
    for sec in all_sectors:
        members = [s for s, secs in sector_map.items() if sec in secs and s in stock_data["D"]]
        rows = build_change_table(stock_data["D"], members)
        if not rows:
            continue
        sector_stocks[sec] = {
            "top5": sorted(rows, key=lambda r: r["change"], reverse=True)[:5],
            "bottom5": sorted(rows, key=lambda r: r["change"])[:5],
            "count": len(rows),
            "avg_change": round(sum(r["change"] for r in rows) / len(rows), 2),
        }

    # ---- Momentum streaks ----
    up_rows, down_rows = [], []
    for sym in fno_symbols:
        df = stock_data["D"].get(sym)
        up, down = closing_streak(df, "up"), closing_streak(df, "down")
        if up >= MOMENTUM_MIN_STREAK:
            up_rows.append({"symbol": sym, "strength": up})
        if down >= MOMENTUM_MIN_STREAK:
            down_rows.append({"symbol": sym, "strength": down})
    up_rows.sort(key=lambda r: r["strength"], reverse=True)
    down_rows.sort(key=lambda r: r["strength"], reverse=True)

    # ---- RSI multi-timeframe scanner ----
    rsi_rows = run_rsi_scanner(stock_data)

    # ---- Intraday first-break signal scan (last 7 days) ----
    intraday_events = run_intraday_scan(stock_data, fno_symbols)

    result = {
        "generated_at": datetime.now().isoformat(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "meta": {
            "fno_count": len(fno_symbols),
            "broader_count": len(broader_market),
            "sector_index_count": len(sector_performance),
            "sectors_mapped": len(sector_stocks),
            "symbol_map_loaded": bool(sector_map),
        },
        "broader_market": broader_market,
        "sector_performance": sector_performance,
        "sector_stocks": sector_stocks,
        "fno": {"all": fno_change, "top5": top5, "bottom5": bottom5},
        "advance_decline": {"advance": adv, "decline": dec, "unchanged": unch},
        "momentum_streaks": {"up": up_rows, "down": down_rows},
        "rsi_scanner": rsi_rows,
        "intraday_events": intraday_events,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"\n✅ wrote {out_path}")
    print(f"   FNO: {len(fno_symbols)} | Broader: {len(broader_market)} | "
          f"Sector idx: {len(sector_performance)} | Sectors mapped: {len(sector_stocks)} | "
          f"RSI rows: {len(rsi_rows)} | Intraday events: {len(intraday_events)}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
