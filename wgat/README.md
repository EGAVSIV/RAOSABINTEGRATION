# Master Scanner — Dow Theory + WGAT

Combines the two original Streamlit apps (`DOW.py` and `WGAT.py`) into a
headless scan pipeline that writes JSON, plus a static two-tab HTML/CSS/JS
dashboard that reads that JSON. No Streamlit is needed to view results
anymore — the dashboard is a plain static site.

## 1. Folder layout

Put this `wgat` folder **inside** the same root folder that already
contains your parquet data:

```
Root/
├── stock_data_15/      <symbol>.parquet   (15 Min candles)
├── stock_data_1H/      <symbol>.parquet   (1 Hour candles)
├── stock_data_D/       <symbol>.parquet   (Daily candles)
├── stock_data_W/       <symbol>.parquet   (Weekly candles)
├── stock_data_M/       <symbol>.parquet   (Monthly candles)
└── wgat/                                   <- this folder
    ├── common.py
    ├── indicators.py
    ├── dow_scan.py
    ├── wgat_scan.py
    ├── parquet_to_json.py
    ├── run_all.py
    ├── index.html
    ├── style.css
    ├── app.js
    ├── README.md
    └── data/
        ├── dow_results.json
        ├── wgat_results.json
        ├── manifest.json
        └── raw/
            ├── stock_data_15/<symbol>.json
            ├── stock_data_1H/<symbol>.json
            ├── stock_data_D/<symbol>.json
            ├── stock_data_W/<symbol>.json
            └── stock_data_M/<symbol>.json
```

Every parquet file needs a date/datetime index (or a `date`/`datetime`
column) and `open`, `high`, `low`, `close` columns (`volume` optional,
column names are case-insensitive).

## 2. Install dependencies

```bash
cd Root/wgat
pip install pandas numpy pyarrow --break-system-packages
```

`talib` is **not required** — `indicators.py` reimplements EMA, MACD, RSI
and ADX in pure pandas/numpy (same formulas TA-Lib uses: Wilder smoothing
for RSI/ADX), since TA-Lib's C library is often painful to install.

## 3. Run the scans

One command refreshes everything the dashboard needs:

```bash
python run_all.py --root .. --date 2026-08-28
```

- `--root` — the folder that directly contains `stock_data_*` (defaults to
  the parent of `wgat/`, i.e. you can usually omit it).
- `--date` — scan as-of date (defaults to today). Both scans only look at
  candles up to and including this date, exactly like the original apps'
  date picker.
- `--skip-raw` — skip regenerating the OHLC JSON used for the in-dashboard
  price sparklines (faster re-runs when you only need updated signals).
- `--raw-timeframes Daily Weekly Monthly` — limit which timeframes get
  converted to raw JSON (default: all five).
- `--raw-bars 300` — how many trailing candles per symbol to keep in the
  raw JSON (default 300, use `0` for full history).

This writes/overwrites:
- `data/dow_results.json` — Dow Theory swing structure + multi-level Fib
  entries, scanned across **all five timeframes** in one file.
- `data/wgat_results.json` — Wave-vs-Tide MACD alignment + EMA/RSI/ADX
  momentum & swing signals (Daily vs Weekly vs Monthly, same as the
  original `WGAT.py` — this strategy is defined around that specific
  timeframe relationship, so it doesn't run separately per 15 Min/1 Hour).
- `data/raw/<timeframe>/<symbol>.json` — trimmed OHLC series per symbol,
  used only to draw the small price chart when you expand a row.
- `data/manifest.json` — small summary (row counts, scan date, generated
  timestamp) for quick sanity checks / automation.

You can also run either scan alone:

```bash
python dow_scan.py --root .. --date 2026-08-28
python wgat_scan.py --root .. --date 2026-08-28
python parquet_to_json.py --root .. --timeframes Daily Weekly Monthly --bars 300
```

### Automating daily refresh

Schedule `run_all.py` (cron / Windows Task Scheduler / Streamlit-independent
script) to run after your data pipeline updates the parquet files each day,
then just refresh the dashboard in the browser.

## 4. View the dashboard

Browsers block `fetch()` of local JSON files opened directly as
`file://...`, so serve the folder over HTTP:

```bash
cd Root/wgat
python -m http.server 8000
```

Then open **http://localhost:8000** in your browser.

The dashboard has two tabs:

- **DOW THEORY** — filter by timeframe, trend bucket (Uptrend / Downtrend /
  Reversal.../ Triangle-Sideways) and Fib entry type; click a row to see
  every Fib retracement price level plus a mini price chart.
- **WGAT** — filter by Wave-vs-Tide category and by
  Bullish/Bearish Momentum/Swing; click a row to see EMA13/50/100, RSI, ADX
  and a mini price chart.

Both tables are sortable (click any column header) and searchable by
symbol. The scrolling strip under the top bar shows live counts for the
currently filtered view.

## 5. Demo data included

`data/` currently ships with output generated from **synthetic placeholder
data** (random walks for 8 dummy symbols) purely so you can open
`index.html` immediately and see the dashboard working end-to-end. The
first time you run `python run_all.py --root .. --date <your date>` against
your real `stock_data_*` parquet files, these demo JSON files are
overwritten with your real scan results.

## 6. Notes / design choices

- All scan **logic** (swing detection, HH/HL/LH/LL labelling, trend bucket
  classification, Fib level + entry-zone math, MACD tick trend, EMA/RSI/ADX
  momentum & swing rules) is copied unchanged from `DOW.py` / `WGAT.py` —
  only the interface changed (Streamlit UI → JSON files → static HTML).
- Column keys in the JSON are lower-cased/underscored versions of the
  original Streamlit column names (e.g. `"61.8% Bull"` → `618pct_bull`,
  `"Category 1"` → `category_1`) so they're safe to use as JS object keys.
- `run_all.py` is idempotent — re-running it just overwrites the JSON with
  a fresh scan as-of the given date.
