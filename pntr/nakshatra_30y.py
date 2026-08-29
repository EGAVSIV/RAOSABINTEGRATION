#!/usr/bin/env python3
"""Generate Moon Nakshatra transition timings for the next 30 years.

IST is used throughout. Swiss Ephemeris is configured to sidereal Lahiri,
matching the existing FNO_REVERSAL_P&T.py implementation.

Output:
    pntr/data/moon_nakshatra_30y.json
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import swisseph as swe

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pntr" / "data" / "moon_nakshatra_30y.json"

NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishtha", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]
NAK_SIZE = 360.0 / 27.0
FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
STEP_MINUTES = 10
REFINE_SECONDS = 1

swe.set_sid_mode(swe.SIDM_LAHIRI)


def jd_from_ist(value: dt.datetime) -> float:
    utc = value.astimezone(dt.timezone.utc)
    return swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60 + utc.second / 3600)


def moon_longitude(value: dt.datetime) -> float:
    pos, _ = swe.calc_ut(jd_from_ist(value), swe.MOON, FLAGS)
    return pos[0] % 360.0


def nak_index(lon: float) -> int:
    return min(26, int(lon // NAK_SIZE))


def nak_pada(lon: float) -> tuple[str, int]:
    idx = nak_index(lon)
    inside = lon - idx * NAK_SIZE
    pada = min(4, int(inside / (NAK_SIZE / 4.0)) + 1)
    return NAKSHATRAS[idx], pada


def unwrap_forward(prev: float, curr: float) -> float:
    return curr if curr >= prev else curr + 360.0


def refine_boundary(a: dt.datetime, b: dt.datetime, target_index: int) -> dt.datetime:
    """Binary-search a Nakshatra boundary to one-second resolution."""
    # Target boundary is the first longitude belonging to target_index.
    boundary = target_index * NAK_SIZE
    for _ in range(24):
        if (b - a).total_seconds() <= REFINE_SECONDS:
            break
        m = a + (b - a) / 2
        la = moon_longitude(a)
        lm = moon_longitude(m)
        # Normalize forward from la to lm.
        lm_u = unwrap_forward(la, lm)
        crossed = lm_u >= boundary if la < boundary else lm_u >= boundary + 360.0
        if crossed:
            b = m
        else:
            a = m
    return b.astimezone(IST).replace(microsecond=0)


def generate(start_date: dt.date, end_date: dt.date) -> list[dict]:
    start = dt.datetime.combine(start_date, dt.time(0, 0), tzinfo=IST)
    end = dt.datetime.combine(end_date, dt.time(23, 59, 59), tzinfo=IST)

    rows: list[dict] = []
    t = start
    prev_lon = moon_longitude(t)
    prev_idx = nak_index(prev_lon)

    while t < end:
        nt = min(t + dt.timedelta(minutes=STEP_MINUTES), end)
        curr_lon = moon_longitude(nt)
        curr_idx = nak_index(curr_lon)

        if curr_idx != prev_idx:
            # If there are multiple boundaries across a coarse interval, walk them.
            idx = prev_idx
            cursor_a = t
            while idx != curr_idx:
                target = (idx + 1) % 27
                boundary_dt = refine_boundary(cursor_a, nt, target)
                from_nak = NAKSHATRAS[idx]
                to_nak = NAKSHATRAS[target]
                lon_at = moon_longitude(boundary_dt)
                rows.append({
                    "datetime_ist": boundary_dt.isoformat(),
                    "event": "Moon Nakshatra Change",
                    "from": from_nak,
                    "to": to_nak,
                    "to_pada": nak_pada(lon_at)[1],
                })
                idx = target
                cursor_a = boundary_dt + dt.timedelta(seconds=1)
        prev_lon = curr_lon
        prev_idx = curr_idx
        t = nt

    return rows


def main() -> None:
    today = dt.datetime.now(IST).date()
    end = today + dt.timedelta(days=365 * 30 + 8)
    rows = generate(today, end)
    payload = {
        "generated_at_ist": dt.datetime.now(IST).isoformat(timespec="seconds"),
        "start_date": today.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "Asia/Kolkata",
        "ayanamsha": "Lahiri",
        "event_count": len(rows),
        "events": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows):,} Nakshatra transitions -> {OUT}")


if __name__ == "__main__":
    main()
