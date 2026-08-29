#!/usr/bin/env python3
"""Generate Moon Pada transition timings for the next 30 years.

Uses the same sidereal Lahiri Swiss Ephemeris setup as the existing FNO scanner.
Output: pntr/data/moon_pada_30y.json
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import swisseph as swe

IST = ZoneInfo("Asia/Kolkata")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pntr" / "data" / "moon_pada_30y.json"
NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni",
    "Uttara Phalguni", "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha",
    "Jyeshtha", "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana",
    "Dhanishtha", "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati"
]
NAK_SIZE = 360.0 / 27.0
PADA_SIZE = NAK_SIZE / 4.0
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


def index_for(lon: float) -> int:
    return min(107, int(lon / PADA_SIZE))


def details(lon: float) -> tuple[int, int, str, int]:
    idx = min(107, int(lon / PADA_SIZE))
    nak_idx = idx // 4
    pada = idx % 4 + 1
    return idx, nak_idx, NAKSHATRAS[nak_idx], pada


def crossed(prev_lon: float, curr_lon: float, boundary: float) -> bool:
    # Moon normally moves forward. Work with an unwrapped current longitude.
    curr_u = curr_lon if curr_lon >= prev_lon else curr_lon + 360.0
    bound = boundary
    while bound < prev_lon:
        bound += 360.0
    return curr_u >= bound


def refine(a: dt.datetime, b: dt.datetime, boundary: float) -> dt.datetime:
    for _ in range(25):
        if (b - a).total_seconds() <= REFINE_SECONDS:
            break
        m = a + (b - a) / 2
        la = moon_longitude(a)
        lm = moon_longitude(m)
        if crossed(la, lm, boundary):
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
    prev_idx = index_for(prev_lon)

    while t < end:
        nt = min(t + dt.timedelta(minutes=STEP_MINUTES), end)
        curr_lon = moon_longitude(nt)
        curr_idx = index_for(curr_lon)
        if curr_idx != prev_idx:
            # Handle each boundary in the interval, including wrap at 360°.
            for target in range(prev_idx + 1, curr_idx + 1) if curr_idx > prev_idx else list(range(prev_idx + 1, 108)) + list(range(0, curr_idx + 1)):
                boundary = target * PADA_SIZE
                if target == 0:
                    boundary = 360.0
                event_t = refine(t, nt, boundary)
                _, _, nak, pada = details(boundary % 360.0 if boundary < 360 else 0.0)
                from_idx = (target - 1) % 108
                _, _, from_nak, from_pada = details(from_idx * PADA_SIZE)
                rows.append({
                    "datetime_ist": event_t.isoformat(),
                    "event": "Moon Pada Change",
                    "from_nakshatra": from_nak,
                    "from_pada": from_pada,
                    "to_nakshatra": nak,
                    "to_pada": pada,
                })
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
    print(f"Wrote {len(rows):,} Pada transitions -> {OUT}")


if __name__ == "__main__":
    main()
