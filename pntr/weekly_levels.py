#!/usr/bin/env python3
"""Build weekly ATR-based support/resistance and reversal timing data.

Data sources are repository-local:
  - stockdata_W/*.json : weekly OHLC for weekly price-cycle levels
  - stockdata_D/*.json : daily OHLC for ATR(10), matching FNO_REVERSAL_P&T.py
  - pntr/data/moon_nakshatra_30y.json : precomputed lunar Nakshatra transitions
  - pntr/data/moon_pada_30y.json : precomputed lunar Pada transitions

Output:
  - pntr/data/weekly_levels.json
  - pntr/data/atr_daily.json
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WEEKLY_DIR = ROOT / "stockdata_W"
DAILY_DIR = ROOT / "stockdata_D"
DATA_DIR = ROOT / "pntr" / "data"
OUT_LEVELS = DATA_DIR / "weekly_levels.json"
OUT_ATR = DATA_DIR / "atr_daily.json"

ATR_PERIOD = 10
LEVEL_STEPS = [30, 60, 90, 120, 150]


def load_json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Expected list JSON: {path}")
    return payload


def wilders_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> float | None:
    """TA-Lib compatible Wilder ATR using recursive smoothing.

    Existing FNO code calls ta.ATR(high, low, close, timeperiod=10), so we
    reproduce the standard True Range + Wilder smoothing without requiring TA-Lib.
    """
    if len(df) < period + 1:
        return None
    h = pd.to_numeric(df["high"], errors="coerce").to_numpy(dtype=float)
    l = pd.to_numeric(df["low"], errors="coerce").to_numpy(dtype=float)
    c = pd.to_numeric(df["close"], errors="coerce").to_numpy(dtype=float)
    tr = np.full(len(df), np.nan, dtype=float)
    tr[0] = h[0] - l[0]
    for i in range(1, len(df)):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    seed = np.nanmean(tr[1 : period + 1])
    if np.isnan(seed):
        return None
    atr = seed
    for i in range(period + 1, len(tr)):
        atr = ((atr * (period - 1)) + tr[i]) / period
    return float(atr)


def price_cycles(close_price: float, steps: list[float]) -> tuple[list[float], list[float]]:
    res, sup = [], []
    up = down = close_price
    for step in steps:
        up += step
        down -= step
        res.append(round(up, 6))
        sup.append(round(down, 6))
    return res, sup


def latest_daily(path: Path) -> tuple[pd.DataFrame, float | None, str | None]:
    rows = load_json_rows(path)
    df = pd.DataFrame(rows)
    needed = {"datetime", "open", "high", "low", "close"}
    if not needed.issubset(df.columns):
        return pd.DataFrame(), None, None
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["datetime", "open", "high", "low", "close"]).sort_values("datetime")
    if df.empty:
        return df, None, None
    atr = wilders_atr(df)
    return df, atr, df["datetime"].iloc[-1].isoformat()


def weekly_latest(path: Path) -> tuple[pd.DataFrame, float | None, str | None]:
    rows = load_json_rows(path)
    df = pd.DataFrame(rows)
    needed = {"datetime", "open", "high", "low", "close"}
    if not needed.issubset(df.columns):
        return pd.DataFrame(), None, None
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["datetime", "open", "high", "low", "close"]).sort_values("datetime")
    if df.empty:
        return df, None, None
    return df, float(df["close"].iloc[-1]), df["datetime"].iloc[-1].isoformat()


def build() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    atr_records: list[dict[str, Any]] = []

    for wpath in sorted(WEEKLY_DIR.glob("*.json")):
        symbol = wpath.stem.upper()
        try:
            wdf, weekly_close, weekly_date = weekly_latest(wpath)
            if weekly_close is None:
                continue
            dpath = DAILY_DIR / f"{symbol}.json"
            if not dpath.exists():
                # Preserve index symbols / special symbols even without D data.
                atr = None
                daily_close = None
                daily_date = None
                atr_pct = None
            else:
                ddf, atr, daily_date = latest_daily(dpath)
                daily_close = float(ddf["close"].iloc[-1]) if not ddf.empty else None
                atr_pct = (atr / daily_close * 100.0) if atr is not None and daily_close else None

            r_raw, s_raw = price_cycles(weekly_close, LEVEL_STEPS)
            new_r: list[float] = []
            new_s: list[float] = []
            if daily_close is None:
                new_r = r_raw.copy()
                new_s = s_raw.copy()
            else:
                for value in r_raw:
                    (new_r if value > daily_close else new_s).append(value)
                new_s.extend(s_raw)
            new_r = (new_r + [None] * 5)[:5]
            new_s = (new_s + [None] * 5)[:5]

            records.append({
                "symbol": symbol,
                "weekly_close": round(weekly_close, 6),
                "weekly_bar_date": weekly_date,
                "daily_close": round(daily_close, 6) if daily_close is not None else None,
                "daily_bar_date": daily_date,
                "atr_period": ATR_PERIOD,
                "atr": round(atr, 6) if atr is not None else None,
                "atr_pct": round(atr_pct, 4) if atr_pct is not None else None,
                "resistance": [round(v, 6) if v is not None else None for v in new_r],
                "support": [round(v, 6) if v is not None else None for v in new_s],
                "source_weekly": str(wpath.relative_to(ROOT)).replace("\\", "/"),
                "source_daily": str(dpath.relative_to(ROOT)).replace("\\", "/") if dpath.exists() else None,
            })
            atr_records.append({
                "symbol": symbol,
                "atr_period": ATR_PERIOD,
                "atr": round(atr, 6) if atr is not None else None,
                "atr_pct": round(atr_pct, 4) if atr_pct is not None else None,
                "daily_close": round(daily_close, 6) if daily_close is not None else None,
                "daily_bar_date": daily_date,
            })
        except Exception as exc:
            print(f"WARN {symbol}: {exc}")

    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    OUT_LEVELS.write_text(json.dumps({
        "generated_at_utc": generated,
        "atr_period": ATR_PERIOD,
        "cycle_steps": LEVEL_STEPS,
        "count": len(records),
        "symbols": records,
    }, indent=2), encoding="utf-8")
    OUT_ATR.write_text(json.dumps({
        "generated_at_utc": generated,
        "atr_period": ATR_PERIOD,
        "count": len(atr_records),
        "symbols": atr_records,
    }, indent=2), encoding="utf-8")
    print(f"Wrote {len(records)} weekly level rows")
    print(f"Wrote {len(atr_records)} daily ATR rows")


if __name__ == "__main__":
    build()
