#!/usr/bin/env python3
"""Generate Ascendant sign transition timings for the next 30 years.

Uses IST, Mumbai coordinates and Swiss Ephemeris with Lahiri sidereal mode,
matching the existing FNO_REVERSAL_P&T.py scanner.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import swisseph as swe

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pntr" / "data" / "ascendant_30y.json"

LAT = 19.07598
LON = 72.87766
FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL
STEP_MINUTES = 10
REFINE_SECONDS = 1
SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

swe.set_sid_mode(swe.SIDM_LAHIRI)


def jd_from_ist(value: dt.datetime) -> float:
    utc = value.astimezone(dt.timezone.utc)
    return swe.julday(
        utc.year, utc.month, utc.day,
        utc.hour + utc.minute / 60 + utc.second / 3600,
    )


def asc_longitude(value: dt.datetime) -> float:
    ascmc, _ = swe.houses_ex(jd_from_ist(value), LAT, LON, b"P", FLAGS)
    return ascmc[0] % 360.0


def sign_index(lon: float) -> int:
    return min(11, int(lon // 30.0))


def forward_delta(a: float, b: float) -> float:
    return (b - a) % 360.0


def refine_boundary(a: dt.datetime, b: dt.datetime, boundary: float) -> dt.datetime:
    boundary %= 360.0
    before = asc_longitude(a)
    for _ in range(32):
        if (b - a).total_seconds() <= REFINE_SECONDS:
            break
        m = a + (b - a) / 2
        current = asc_longitude(m)
        if forward_delta(before, current) >= forward_delta(before, boundary):
            b = m
        else:
            a = m
    return b.astimezone(IST).replace(microsecond=0)


def generate(start_date: dt.date, end_date: dt.date) -> list[dict]:
    start = dt.datetime.combine(start_date, dt.time(0, 0), tzinfo=IST)
    end = dt.datetime.combine(end_date, dt.time(23, 59, 59), tzinfo=IST)
    rows: list[dict] = []

    t = start
    prev_lon = asc_longitude(t)
    prev_idx = sign_index(prev_lon)

    while t < end:
        nt = min(t + dt.timedelta(minutes=STEP_MINUTES), end)
        curr_lon = asc_longitude(nt)
        curr_idx = sign_index(curr_lon)

        if curr_idx != prev_idx:
            idx = prev_idx
            cursor = t
            while idx != curr_idx:
                target = (idx + 1) % 12
                event_t = refine_boundary(cursor, nt, target * 30.0)
                rows.append({
                    "datetime_ist": event_t.isoformat(),
                    "event": "Ascendant Change",
                    "from": SIGNS[idx],
                    "to": SIGNS[target],
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
        "location": {"latitude": LAT, "longitude": LON, "name": "Mumbai, India"},
        "event_count": len(rows),
        "events": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(rows):,} Ascendant transitions -> {OUT}")


if __name__ == "__main__":
    main()
