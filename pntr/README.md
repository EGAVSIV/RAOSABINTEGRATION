# PNTR — FNO Weekly Levels + Astro Timing

## Files

- `nakshatra_30y.py` — calculates Moon Nakshatra change timestamps for the next 30 years using Swiss Ephemeris, Lahiri sidereal mode, IST.
- `pada_30y.py` — calculates every Moon Pada boundary/change for the next 30 years.
- `weekly_levels.py` — reads root `stockdata_W/*.json`, calculates weekly cycle S/R levels using the same `30/60/90/120/150` price-cycle logic as `FNO_REVERSAL_P&T.py`, and reads root `stockdata_D/*.json` for daily ATR(10).
- `index.html` — static dashboard consuming generated JSON files.
- `data/` — generated JSON output directory.

## Run from repository root

```bash
python pntr/nakshatra_30y.py
python pntr/pada_30y.py
python pntr/weekly_levels.py
```

Generated files:

```text
pntr/data/moon_nakshatra_30y.json
pntr/data/moon_pada_30y.json
pntr/data/weekly_levels.json
pntr/data/atr_daily.json
```

Then serve the repository root with any static HTTP server and open `pntr/index.html`. For example:

```bash
python -m http.server 8000
```

Open `http://localhost:8000/pntr/`.

## Notes

The existing FNO code uses Swiss Ephemeris Lahiri sidereal settings and computes ATR with TA-Lib on daily OHLC data. The new engine preserves those choices while removing the Streamlit/UI and TradingView dependency from the batch calculations.
