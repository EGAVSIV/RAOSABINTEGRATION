# GEOTRADER — Market Intelligence Terminal

Streamlit has been removed completely. The app is now split into three
independent pieces:

```
project/
├── engine.py            # 1. calculation engine -> writes result.json
├── dashboard.html        # 2. standalone HTML dashboard -> reads result.json
├── requirements.txt      # 3. python dependencies for engine.py
├── stockdata_15/         # 15-minute candles, one .json file per symbol
├── stockdata_1H/         # 1-hour candles
├── stockdata_D/          # Daily candles
├── stockdata_W/          # Weekly candles
├── stockdata_M/          # Monthly candles
└── symbol_map.json       # optional: category + sector per symbol
```

## 1. Data folders (per your screenshot)

Each `stockdata_*` folder holds one JSON file per symbol, e.g.
`stockdata_D/RELIANCE.json`. Any of these shapes are accepted:

```json
[
  {"date": "2026-08-27T00:00:00", "open": 100.1, "high": 101.4, "low": 99.6, "close": 100.9, "volume": 45210},
  ...
]
```

or `{"data": [ {...}, {...} ]}`, or column-arrays `{"date": [...], "open": [...], ...}`.
Column names are matched case-insensitively (`Open`/`open`/`o`, `Date`/`date`/`timestamp`, etc.).
If your JSON already contains `rsi_14`, `bb_upper`, `bb_lower`, `cpr_tc`, `cpr_bc`,
`cam_h4`, `cam_l4`, the engine reuses them instead of recalculating.

## 2. Engine (`engine.py`)

Reads every symbol in every `stockdata_*` folder, computes:

- % change (latest vs previous close)
- RSI(14), Bollinger Bands(20, 2σ), CPR, Camarilla pivots
- Broad market / sector performance tables
- FNO advance/decline, top 5 / bottom 5 gainers & losers
- Sector → stock top5/bottom5 breakdown (needs `symbol_map.json`)
- Momentum streaks (≥2 consecutive up/down closes)
- Multi-timeframe RSI scanner (15m / 1H / D / W / M)
- Intraday first-break events (daily/weekly high-low breaks with RSI /
  Bollinger / CPR / Camarilla confirmation), last 7 days

...and writes everything to `result.json` next to it.

```bash
pip install -r requirements.txt
python engine.py
```

Run it manually whenever you want fresh numbers, or schedule it (cron /
Windows Task Scheduler) to refresh `result.json` automatically, e.g. every
5 minutes during market hours.

### Optional: `symbol_map.json`

Without this file every symbol found in `stockdata_D` is treated as part
of the tradable "FNO" universe, and the Broad Market / Sector Performance
panels are simply left empty (the dashboard shows "no symbols mapped"
instead of crashing). To populate those panels, add a `symbol_map.json`
next to `engine.py`:

```json
{
  "NIFTY50":   {"category": "broader"},
  "BANKNIFTY": {"category": "broader"},
  "NIFTYIT":   {"category": "sector", "sector": "IT"},
  "RELIANCE":  {"category": "fno", "sector": "Energy"},
  "TCS":       {"category": "fno", "sector": "IT"}
}
```

`category` is one of `broader`, `sector`, `fno`. `sector` groups FNO
stocks for the sector-explorer chart on the dashboard. An `.xlsx`
sector-map file (same two-column format the old app used) is also still
supported as a fallback — see `SYMBOL_MAP_CANDIDATES` at the top of
`engine.py` for the exact filenames/paths it checks.

## 3. Dashboard (`dashboard.html`)

A single, self-contained HTML file — no build step, no server-side code.
It fetches `result.json` with `fetch()`, so it must be served over HTTP
(browsers block `fetch` on `file://` pages):

```bash
python -m http.server 8000
```

Then open **http://localhost:8000/dashboard.html**. Click **Refresh** in
the top bar any time after re-running `engine.py` to pull the latest
`result.json` without reloading the page.

### What's on it
- Ticker tape of FNO top/bottom movers
- KPI strip: symbols tracked, advancing, declining, 7-day intraday events
- Broad market / sector performance / advance-decline charts
- FNO top5 & bottom5 bar chart
- Sector explorer (dropdown → that sector's FNO members)
- Momentum streak badges (up / down)
- RSI scanner table with timeframe + state checkboxes
- Intraday rolling ticker (breakout/breakdown events, last 7 days)

## Notes on what changed from the original file

- All `streamlit`, `st.*`, and `plotly.express` UI code removed.
- The Hindi motivational-quotes ticker, background image, and logo were
  UI decoration tied to Streamlit and were not carried over — the new
  dashboard has its own visual identity instead.
- Data source changed from per-timeframe **parquet** files under
  `market_data/{broader_index,sector_index,fno}/{tf}/*.parquet` to
  per-symbol **JSON** files under `stockdata_15 / stockdata_1H /
  stockdata_D / stockdata_W / stockdata_M`, matching your folder screenshot.
- All indicator math (RSI, Bollinger, CPR, Camarilla, momentum streaks,
  intraday first-break scan) was preserved from the original script.
