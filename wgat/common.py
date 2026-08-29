"""
common.py
Shared helpers used by dow_scan.py, wgat_scan.py and parquet_to_json.py.

Folder layout expected (relative to --root, default is the parent of this
"wgat" folder):

    <root>/stock_data_15/<SYMBOL>.parquet
    <root>/stock_data_1H/<SYMBOL>.parquet
    <root>/stock_data_D/<SYMBOL>.parquet
    <root>/stock_data_W/<SYMBOL>.parquet
    <root>/stock_data_M/<SYMBOL>.parquet

Every parquet file is expected to have a DatetimeIndex (or a column that can
be parsed as one) and at least open/high/low/close columns. volume is
optional.
"""

from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, date

import numpy as np
import pandas as pd

# Timeframe label -> folder name. Order matters for the UI dropdowns.
TIMEFRAME_FOLDERS = {
    "15 Min": "stock_data_15",
    "1 Hour": "stock_data_1H",
    "Daily": "stock_data_D",
    "Weekly": "stock_data_W",
    "Monthly": "stock_data_M",
}

REQUIRED_COLS = ["open", "high", "low", "close"]


def resolve_root(root: str | None) -> Path:
    """Root is the folder that directly contains stock_data_* folders.
    Defaults to the parent of this file's folder (Root/wgat/common.py -> Root)."""
    if root:
        return Path(root).resolve()
    return Path(__file__).resolve().parent.parent


def data_folder(root: Path, timeframe_label: str) -> Path:
    return root / TIMEFRAME_FOLDERS[timeframe_label]


def list_symbols(folder: Path) -> list[str]:
    if not folder.exists():
        return []
    return sorted({f.stem for f in folder.glob("*.parquet")})


def load_df(folder: Path, symbol: str) -> pd.DataFrame:
    df = pd.read_parquet(folder / f"{symbol}.parquet")

    # normalize column names
    df.columns = [str(c).strip().lower() for c in df.columns]

    # normalize the index to a DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        date_col = None
        for cand in ("date", "datetime", "timestamp", "time"):
            if cand in df.columns:
                date_col = cand
                break
        if date_col is not None:
            df = df.set_index(date_col)
        df.index = pd.to_datetime(df.index)
    else:
        df.index = pd.to_datetime(df.index)

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"{symbol}: missing columns {missing}")

    df = df.sort_index()
    return df


def filter_until_date(df: pd.DataFrame, until) -> pd.DataFrame:
    until = pd.to_datetime(until)
    return df[df.index <= until].copy()


def latest_date_for_folder(folder: Path):
    if not folder.exists():
        return None
    latest = None
    for f in folder.glob("*.parquet"):
        try:
            df = pd.read_parquet(f, columns=None)
            df.index = pd.to_datetime(df.index)
            m = df.index.max()
        except Exception:
            continue
        if latest is None or m > latest:
            latest = m
    return latest


class NpEncoder(json.JSONEncoder):
    """json.dump encoder that understands numpy/pandas scalar types."""

    def default(self, o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            if np.isnan(o):
                return None
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, (pd.Timestamp, datetime, date)):
            return o.isoformat()
        if isinstance(o, np.ndarray):
            return o.tolist()
        if pd.isna(o):
            return None
        return super().default(o)


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, cls=NpEncoder, allow_nan=False)
