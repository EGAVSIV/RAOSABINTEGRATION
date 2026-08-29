#!/usr/bin/env python3
"""Generate Moon Nakshatra transition timings for the next 30 years.

Uses IST and Swiss Ephemeris Lahiri sidereal mode, matching the existing
FNO_REVERSAL_P&T.py scanner. The calculation is boundary-driven: the exact
Nakshatra boundary is located by binary search, rather than by reporting the
coarse scan step.
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
    return swe.julday(
        utc.year, utc.month, utc.day,
        utc.hour + utc.minute / 60 + utc.second / 3600,
    )


def moon_longitude(value: dt.datetime) -> float:
    pos, _ = swe.calc_ut(jd_from_ist(value), swe.MOON, FLAGS)
    return pos[0] % 360.0


def nak_index(lon: float) -> int:
    return min(26, int(lon // NAK_SIZE))


def get_nak_pada(lon: float) -> tuple[str, int]:
    i = nak_index(lon)
    inside = lon - i * NAK_SIZE
    pada = min(4, int(inside / (NAK_SIZE / 4.0)) + 1)
    return NAKSHATRAS[i], pada


def forward_delta(a: float, b: float) -> float:
    """Forward angular distance from a to b in [0, 360)."""
    return (b - a) % 360.0


def boundary_crossed(a: float, b: float, boundary: float) -> bool:
    return forward_delta(a, b) >= forward_delta(a, boundary % 360.0)


def refine_boundary(a: dt.datetime, b: dt.datetime, boundary: float) -> dt.datetime:
    """Binary-search the first instant at which longitude reaches boundary."""
    boundary %= 360.0
    before = moon_longitude(a)
    # Caller guarantees the boundary occurs between a and b.
    for _ in range(32):
        if (b - a).total_seconds() <= REFINE_SECONDS:
            break
        m = a + (b - a) / 2
        mlon = moon_longitude(m)
        if forward_delta(before, mlon) >= forward_delta(before, boundary):
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
            idx = prev_idx
            cursor = t
            while idx != curr_idx:
                target = (idx + 1) % 27
                boundary = target * NAK_SIZE
                event_t = refine_boundary(cursor, nt, boundary)
                rows.append({
                    "datetime_ist": event_t.isoformat(),
                    "event": "Moon Nakshatra Change",
                    "from": NAKSHATRAS[idx],
                    "to": NAKSHATRAS[target],
                    "to_pada": get_nak_pada(moon_longitude(event_t))[1],
                })
                idx = target
                cursor = event_t + dt.timedelta(seconds=1)
                if cursor >= nt:
                    break

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
