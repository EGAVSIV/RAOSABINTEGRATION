"""
================================================================================
 MARKET DASHBOARD - CALCULATION ENGINE
================================================================================
Reads OHLCV data (JSON files, one per symbol, per timeframe) from the folders:

    stockdata_15   -> 15 minute candles
    stockdata_1H   -> 1 hour candles
    stockdata_D    -> Daily candles
    stockdata_W    -> Weekly candles
    stockdata_M    -> Monthly candles

...calculates every parameter the dashboard needs (RSI, Bollinger Bands, CPR,
Camarilla pivots, % change, advance/decline, sector performance, momentum
streaks, multi-timeframe RSI scanner, intraday breakout events) and writes a
single consolidated file: result.json

This script has NO UI code in it (no Streamlit). Run it manually or on a
schedule (cron / Task Scheduler) and the dashboard.html will pick up the
latest result.json.

    python engine.py

================================================================================
"""

import os
import json
import glob
import traceback
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# =====================================================================
# CONFIG
# =====================================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TF_FOLDERS = {
    "15m": os.path.join(BASE_DIR, "stockdata_15"),
    "1H":  os.path.join(BASE_DIR, "stockdata_1H"),
    "D":   os.path.join(BASE_DIR, "stockdata_D"),
    "W":   os.path.join(BASE_DIR, "stockdata_W"),
    "M":   os.path.join(BASE_DIR, "stockdata_M"),
}

OUTPUT_FILE = os.path.join(BASE_DIR, "result.json")

# Optional symbol -> {"category": "broader"|"sector"|"fno", "sector": "IT"} map.
# Looked up in this order; first one found is used. If none exist, every
# symbol found in stockdata_D is treated as an "fno" (tradable stock) symbol,
# and the Broader Market / Sector Performance sections are simply left empty
# instead of crashing - so the engine always runs even without a mapping file.
SYMBOL_MAP_CANDIDATES = [
    os.path.join(BASE_DIR, "config", "symbol_map.json"),
    os.path.join(BASE_DIR, "symbol_map.json"),
    os.path.join(BASE_DIR, "config", "FNOSECTOR.xlsx"),
    os.path.join(BASE_DIR, "FNOSECTOR.xlsx"),
    os.path.join(BASE_DIR, "market_data", "FNOSECTOR.xlsx"),
]

RSI_PERIOD = 14
BB_PERIOD = 20
BB_STD = 2
MOMENTUM_MAX_DAYS = 10
MOMENTUM_MIN_STREAK = 2
INTRADAY_LOOKBACK_DAYS = 7
INTRADAY_TFS = ["15m", "1H"]


# =====================================================================
# DATA LOADING (flexible JSON schema)
# =====================================================================
DATE_KEYS = ["datetime", "date", "timestamp", "time", "Date", "Datetime", "Timestamp"]
COL_ALIASES = {
    "open":   ["open", "o", "Open", "OPEN"],
    "high":   ["high", "h", "High", "HIGH"],
    "low":    ["low", "l", "Low", "LOW"],
    "close":  ["close", "c", "Close", "CLOSE"],
    "volume": ["volume", "v", "vol", "Volume", "VOLUME"],
}


def _first_present(d, keys):
    for k in keys:
        if k in d:
            return k
    return None


def load_symbol_json(path):
    """Load one symbol's JSON file into a clean, sorted OHLCV DataFrame
    indexed by datetime. Supports either:
      - a list of row-dicts:      [{"date": "...", "open": 1, ...}, ...]
      - a dict of column arrays:  {"date": [...], "open": [...], ...}
      - a dict wrapping records:  {"data": [ {...}, {...} ]}
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
        raw = raw["data"]

    if isinstance(raw, dict):
        # dict-of-arrays -> DataFrame directly
        df = pd.DataFrame(raw)
    elif isinstance(raw, list):
        df = pd.DataFrame(raw)
    else:
        raise ValueError(f"Unrecognized JSON structure in {path}")

    if df.empty:
        return df

    date_col = _first_present(df.columns, DATE_KEYS)
    if date_col is None:
        raise ValueError(f"No date/datetime column found in {path}")

    df["datetime"] = pd.to_datetime(df[date_col], errors="coerce", utc=False)
    df = df.dropna(subset=["datetime"])

    rename_map = {}
    for std_name, aliases in COL_ALIASES.items():
        col = _first_present(df.columns, aliases)
        if col:
            rename_map[col] = std_name
    df = df.rename(columns=rename_map)

    for req in ["open", "high", "low", "close"]:
        if req not in df.columns:
            raise ValueError(f"Missing '{req}' column in {path}")
        df[req] = pd.to_numeric(df[req], errors="coerce")

    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce")

    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_values("datetime").set_index("datetime")
    return df


def list_symbols(folder):
    if not os.path.isdir(folder):
        return []
    return sorted(
        os.path.splitext(os.path.basename(p))[0]
        for p in glob.glob(os.path.join(folder, "*.json"))
    )


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
    rsi = rsi.where(avg_loss != 0, 100.0)
    return rsi


def compute_bollinger(close, period=BB_PERIOD, num_std=BB_STD):
    mid = close.rolling(period).mean()
    std = close.rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def compute_pivots(df):
    """CPR (Central Pivot Range) + Camarilla levels for each row, derived
    from the PREVIOUS row's High/Low/Close - i.e. the levels that apply
    while that row's candle is trading."""
    ph = df["high"].shift(1)
    pl = df["low"].shift(1)
    pc = df["close"].shift(1)

    pivot = (ph + pl + pc) / 3
    bc = (ph + pl) / 2
    tc = (pivot - bc) + pivot

    rng = (ph - pl)
    cam_h3 = pc + rng * 1.1 / 4
    cam_h4 = pc + rng * 1.1 / 2
    cam_l3 = pc - rng * 1.1 / 4
    cam_l4 = pc - rng * 1.1 / 2

    return pivot, tc, bc, cam_h3, cam_h4, cam_l3, cam_l4


def enrich(df):
    """Add rsi_14 / bollinger / cpr / camarilla columns to a raw OHLCV df,
    unless those columns already exist in the source JSON (then keep them)."""
    if df.empty:
        return df
    df = df.copy()

    if "rsi_14" not in df.columns:
        df["rsi_14"] = compute_rsi(df["close"])

    if "bb_upper" not in df.columns or "bb_lower" not in df.columns:
        up, mid, lo = compute_bollinger(df["close"])
        df["bb_upper"], df["bb_mid"], df["bb_lower"] = up, mid, lo

    needed_pivot_cols = ["cpr_pivot", "cpr_tc", "cpr_bc", "cam_h3", "cam_h4", "cam_l3", "cam_l4"]
    if any(c not in df.columns for c in needed_pivot_cols):
        pivot, tc, bc, h3, h4, l3, l4 = compute_pivots(df)
        df["cpr_pivot"], df["cpr_tc"], df["cpr_bc"] = pivot, tc, bc
        df["cam_h3"], df["cam_h4"], df["cam_l3"], df["cam_l4"] = h3, h4, l3, l4

    return df


# =====================================================================
# SYMBOL CATEGORY MAP (optional)
# =====================================================================
def load_symbol_map():
    """Returns dict: symbol -> {"category": "broader"/"sector"/"fno", "sector": str or None}"""
    for path in SYMBOL_MAP_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            if path.endswith(".json"):
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                out = {}
                for sym, v in raw.items():
                    if isinstance(v, str):
                        out[sym] = {"category": "sector", "sector": v}
                    else:
                        out[sym] = {
                            "category": v.get("category", "fno"),
                            "sector": v.get("sector"),
                        }
                print(f"[symbol map] loaded {len(out)} symbols from {path}")
                return out
            elif path.endswith(".xlsx"):
                sm = pd.read_excel(path)
                sm.columns = sm.columns.astype(str).str.strip().str.lower()
                stock_col = next((c for c in sm.columns if "stock" in c), None)
                sector_col = next((c for c in sm.columns if "sector" in c), None)
                if not stock_col or not sector_col:
                    continue
                sm = sm.rename(columns={stock_col: "Stock", sector_col: "Sector"})
                sm["Sector"] = sm["Sector"].astype(str).str.split(",")
                sm = sm.explode("Sector")
                sm["Sector"] = sm["Sector"].str.strip()
                out = {}
                for _, row in sm.iterrows():
                    out[str(row["Stock"]).strip()] = {"category": "fno", "sector": row["Sector"]}
                print(f"[symbol map] loaded {len(out)} symbols from {path}")
                return out
        except Exception as e:
            print(f"[symbol map] failed to read {path}: {e}")
    print("[symbol map] none found - every symbol will be treated as category 'fno'")
    return {}


# =====================================================================
# CACHE: load every symbol / timeframe once
# =====================================================================
def load_all():
    """Returns nested dict: data[tf][symbol] = enriched DataFrame"""
    data = {tf: {} for tf in TF_FOLDERS}
    for tf, folder in TF_FOLDERS.items():
        for symbol in list_symbols(folder):
            path = os.path.join(folder, f"{symbol}.json")
            try:
                df = load_symbol_json(path)
                if df.empty:
                    continue
                data[tf][symbol] = enrich(df)
            except Exception as e:
                print(f"[load] skipping {tf}/{symbol}: {e}")
    return data


# =====================================================================
# CALCULATIONS
# =====================================================================
def pct_change_last_two(df):
    if df is None or len(df) < 2:
        return 0.0
    p, c = df["close"].iloc[-2], df["close"].iloc[-1]
    if pd.isna(p) or pd.isna(c) or p == 0:
        return 0.0
    return round(((c - p) / p) * 100, 2)


def build_change_table(daily_data, symbols):
    rows = []
    for sym in symbols:
        df = daily_data.get(sym)
        rows.append({"symbol": sym, "change": pct_change_last_two(df)})
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


def run_rsi_scanner(data):
    rows = []
    tf_labels = {"15m": "15 MIN", "1H": "60 MIN", "D": "DAY"}

    for tf, label in tf_labels.items():
        for symbol, df in data.get(tf, {}).items():
            if len(df) < 2 or "rsi_14" not in df.columns:
                continue
            curr, prev = df["rsi_14"].iloc[-1], df["rsi_14"].iloc[-2]
            if pd.isna(curr) or pd.isna(prev):
                continue
            rows.append({
                "symbol": symbol, "tf": label,
                "rsi": round(float(curr), 2),
                "state": rsi_state(curr, prev),
            })

    for tf, label in [("W", "WEEK"), ("M", "MONTH")]:
        for symbol, df in data.get(tf, {}).items():
            if len(df) < 2 or "rsi_14" not in df.columns:
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
        "day_high": prev["high"],
        "day_low": prev["low"],
        "cpr_tc": prev.get("cpr_tc"),
        "cpr_bc": prev.get("cpr_bc"),
        "cam_h4": prev.get("cam_h4"),
        "cam_l4": prev.get("cam_l4"),
    }


def evaluate_first_break_intraday(symbol, tf, df_tf, daily_df, weekly_df):
    if len(df_tf) < 2 or "rsi_14" not in df_tf.columns:
        return None
    if len(daily_df) < 2 or len(weekly_df) < 2:
        return None

    daily = get_daily_levels(daily_df)
    prev_week = weekly_df.iloc[-2]
    today = df_tf.index[-1].date()
    primary_triggered = False

    for i in range(1, len(df_tf)):
        prev = df_tf.iloc[i - 1]
        curr = df_tf.iloc[i]
        ts = df_tf.index[i]

        if ts.date() != today:
            continue

        prev_close, curr_close = prev["close"], curr["close"]
        reasons = []
        bull, bear = 0, 0
        primary_triggered = False

        if prev_close < daily["day_high"] and curr_close > daily["day_high"]:
            bull += 1
            primary_triggered = True
            reasons.append(f"Daily High BO @ {ts.strftime('%H:%M')}")
        elif prev_close > daily["day_low"] and curr_close < daily["day_low"]:
            bear += 1
            primary_triggered = True
            reasons.append(f"Daily Low BD @ {ts.strftime('%H:%M')}")
        elif prev_close < prev_week["high"] and curr_close > prev_week["high"]:
            bull += 1
            primary_triggered = True
            reasons.append(f"Weekly High BO @ {ts.strftime('%H:%M')}")
        elif prev_close > prev_week["low"] and curr_close < prev_week["low"]:
            bear += 1
            primary_triggered = True
            reasons.append(f"Weekly Low BD @ {ts.strftime('%H:%M')}")

        if not primary_triggered:
            continue

        rsi_prev, rsi_curr = prev["rsi_14"], curr["rsi_14"]
        if pd.notna(rsi_prev) and pd.notna(rsi_curr):
            if rsi_prev < 60 and rsi_curr > 60:
                bull += 1
                reasons.append(f"RSI > 60 @ {ts.strftime('%H:%M')}")
            if rsi_prev > 40 and rsi_curr < 40:
                bear += 1
                reasons.append(f"RSI < 40 @ {ts.strftime('%H:%M')}")

        if "bb_upper" in df_tf.columns and pd.notna(prev.get("bb_upper")) and pd.notna(curr.get("bb_upper")):
            if prev_close < prev["bb_upper"] and curr_close > curr["bb_upper"]:
                bull += 1
                reasons.append(f"BB Upper BO @ {ts.strftime('%H:%M')}")
        if "bb_lower" in df_tf.columns and pd.notna(prev.get("bb_lower")) and pd.notna(curr.get("bb_lower")):
            if prev_close > prev["bb_lower"] and curr_close < curr["bb_lower"]:
                bear += 1
                reasons.append(f"BB Lower BD @ {ts.strftime('%H:%M')}")

        if daily["cpr_tc"] and pd.notna(daily["cpr_tc"]) and prev_close < daily["cpr_tc"] and curr_close > daily["cpr_tc"]:
            bull += 1
            reasons.append(f"CPR TC BO @ {ts.strftime('%H:%M')}")
        if daily["cpr_bc"] and pd.notna(daily["cpr_bc"]) and prev_close > daily["cpr_bc"] and curr_close < daily["cpr_bc"]:
            bear += 1
            reasons.append(f"CPR BC BD @ {ts.strftime('%H:%M')}")

        if daily["cam_h4"] and pd.notna(daily["cam_h4"]) and prev_close < daily["cam_h4"] and curr_close > daily["cam_h4"]:
            bull += 1
            reasons.append(f"Cam H4 BO @ {ts.strftime('%H:%M')}")
        if daily["cam_l4"] and pd.notna(daily["cam_l4"]) and prev_close > daily["cam_l4"] and curr_close < daily["cam_l4"]:
            bear += 1
            reasons.append(f"Cam L4 BD @ {ts.strftime('%H:%M')}")

        if bull >= 2 and bull > bear:
            return {"symbol": symbol, "tf": tf, "signal": "BUY", "ts": ts.isoformat(), "reasons": reasons}
        if bear >= 2 and bear > bull:
            return {"symbol": symbol, "tf": tf, "signal": "SELL", "ts": ts.isoformat(), "reasons": reasons}

        break

    return None


def run_intraday_scan(data, universe_symbols):
    events = []
    daily_data = data.get("D", {})

    for symbol in universe_symbols:
        daily_df = daily_data.get(symbol)
        if daily_df is None or len(daily_df) < 2:
            continue

        weekly_df = data.get("W", {}).get(symbol)
        if weekly_df is None or len(weekly_df) < 2:
            weekly_df = daily_df.resample("W-FRI").agg({"high": "max", "low": "min"}).dropna()

        for tf in INTRADAY_TFS:
            df_tf = data.get(tf, {}).get(symbol)
            if df_tf is None:
                continue
            ev = evaluate_first_break_intraday(symbol, tf, df_tf, daily_df, weekly_df)
            if ev:
                events.append(ev)

    cutoff = pd.Timestamp.now() - timedelta(days=INTRADAY_LOOKBACK_DAYS)
    events = [ev for ev in events if pd.Timestamp(ev["ts"]) >= cutoff]
    events.sort(key=lambda x: x["ts"], reverse=True)
    return events


# =====================================================================
# MAIN
# =====================================================================
def main():
    print("=" * 70)
    print("Market Dashboard Engine — starting run:", datetime.now().isoformat())
    print("=" * 70)

    data = load_all()
    symbol_map = load_symbol_map()

    all_daily_symbols = sorted(data.get("D", {}).keys())
    if not all_daily_symbols:
        raise SystemExit(
            f"No daily data found. Expected JSON files inside: {TF_FOLDERS['D']}"
        )

    broader_syms = [s for s in all_daily_symbols if symbol_map.get(s, {}).get("category") == "broader"]
    sector_index_syms = [s for s in all_daily_symbols if symbol_map.get(s, {}).get("category") == "sector"]
    fno_syms = [s for s in all_daily_symbols if symbol_map.get(s, {}).get("category", "fno") == "fno"]
    if not symbol_map:
        # no map at all -> everything is the "fno" tradable universe
        fno_syms = all_daily_symbols

    daily_data = data["D"]

    # ---- Broader market ----
    broader_market = build_change_table(daily_data, broader_syms)

    # ---- Sector performance (index-level) ----
    sector_performance = build_change_table(daily_data, sector_index_syms)

    # ---- FNO universe % change / gainers-losers / advance-decline ----
    fno_change = build_change_table(daily_data, fno_syms)
    fno_sorted = sorted(fno_change, key=lambda r: r["change"], reverse=True)
    top5 = fno_sorted[:5]
    bottom5 = sorted(fno_change, key=lambda r: r["change"])[:5]

    adv = sum(1 for r in fno_change if r["change"] > 0)
    dec = sum(1 for r in fno_change if r["change"] < 0)
    unch = sum(1 for r in fno_change if r["change"] == 0)

    # ---- Sector -> stock groups (top5/bottom5 per sector) ----
    sector_names = sorted({v.get("sector") for v in symbol_map.values() if v.get("sector")})
    sector_stocks = {}
    for sec in sector_names:
        members = [s for s, v in symbol_map.items() if v.get("sector") == sec and s in daily_data]
        rows = build_change_table(daily_data, members)
        if not rows:
            continue
        rows_sorted = sorted(rows, key=lambda r: r["change"], reverse=True)
        sector_stocks[sec] = {
            "top5": rows_sorted[:5],
            "bottom5": sorted(rows, key=lambda r: r["change"])[:5],
        }

    # ---- Momentum streaks ----
    up_rows, down_rows = [], []
    for sym in fno_syms:
        df = daily_data.get(sym)
        up = closing_streak(df, "up")
        down = closing_streak(df, "down")
        if up >= MOMENTUM_MIN_STREAK:
            up_rows.append({"symbol": sym, "strength": up})
        if down >= MOMENTUM_MIN_STREAK:
            down_rows.append({"symbol": sym, "strength": down})
    up_rows.sort(key=lambda r: r["strength"], reverse=True)
    down_rows.sort(key=lambda r: r["strength"], reverse=True)

    # ---- RSI scanner ----
    rsi_rows = run_rsi_scanner(data)

    # ---- Intraday breakout events ----
    intraday_events = run_intraday_scan(data, fno_syms)

    result = {
        "generated_at": datetime.now().isoformat(),
        "meta": {
            "total_symbols": len(all_daily_symbols),
            "broader_count": len(broader_syms),
            "sector_index_count": len(sector_index_syms),
            "fno_count": len(fno_syms),
            "sector_map_loaded": bool(symbol_map),
        },
        "broader_market": broader_market,
        "sector_performance": sector_performance,
        "sector_stocks": sector_stocks,
        "fno": {
            "all": fno_change,
            "top5": top5,
            "bottom5": bottom5,
        },
        "advance_decline": {"advance": adv, "decline": dec, "unchanged": unch},
        "momentum_streaks": {"up": up_rows, "down": down_rows},
        "rsi_scanner": rsi_rows,
        "intraday_events": intraday_events,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    print(f"\n✅ result.json written -> {OUTPUT_FILE}")
    print(f"   Symbols: {len(all_daily_symbols)} | FNO: {len(fno_syms)} | "
          f"Broader: {len(broader_syms)} | Sector-index: {len(sector_index_syms)}")
    print(f"   RSI rows: {len(rsi_rows)} | Intraday events (7d): {len(intraday_events)}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
