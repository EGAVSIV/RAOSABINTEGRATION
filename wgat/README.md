# Master Scanner — Dow Theory + WGAT

Two self-contained Python scripts (no shared helper modules, no talib,
no parquet) that scan your **existing JSON** candle data and write
`resultdow.json` / `resultwgat.json`, plus a static two-tab HTML/CSS/JS
dashboard that reads those two files. HTML/CSS are unchanged from the
previous version — only the JS data-loading paths were updated.

## 1. Folder layout

Put this `wgat` folder **inside** the same root folder that already
contains your JSON candle data (matches your actual folder names):

```
Root/
├── stockdata_15/     <SYMBOL>.json   (15 Min candles)
├── stockdata_1H/     <SYMBOL>.json   (1 Hour candles)
├── stockdata_D/      <SYMBOL>.json   (Daily candles)
├── stockdata_W/      <SYMBOL>.json   (Weekly candles)
├── stockdata_M/      <SYMBOL>.json   (Monthly candles)
└── wgat/                              <- this folder
    ├── dow_scan.py       (single file — Dow Theory + Fib scan)
    ├── wgat_scan.py      (single file — Wave-vs-Tide scan)
    ├── index.html
    ├── style.css
    ├── app.js
    ├── README.md
    ├── resultdow.json    (written by dow_scan.py)
    └── resultwgat.json   (written by wgat_scan.py)
```

Each `<SYMBOL>.json` is expected to hold a list of candle records:

```json
[
  {"date": "2026-01-02", "open": 101.2, "high": 103.4, "low": 100.1, "close": 102.9, "volume": 15230},
  ...
]
```

Both scripts are tolerant of common variations (short field names
`t/o/h/l/c/v`, a wrapper key like `"data"`/`"records"`, columnar JSON,
etc.) via a single `load_ohlc_json()` function near the top of each
file. **If your JSON schema doesn't match, that's the only function you
need to edit** — nothing else in either script depends on the exact
shape.

## 2. Install dependencies

```bash
pip install pandas numpy --break-system-packages
```

That's it — no `pyarrow`, no `talib`. Each script is fully self-contained
(indicator math, scan logic, and JSON I/O all live in the one file).

## 3. Run the scans

```bash
cd Root/wgat
python dow_scan.py --date 2026-08-28
python wgat_scan.py --date 2026-08-28
```

- `--root` — folder containing `stockdata_*` (defaults to the parent of
  wherever the script lives, i.e. you can omit it when `wgat/` sits
  directly inside `Root/`, as above).
- `--date` — scan as-of date (defaults to today). Only candles up to and
  including this date are considered.
- `dow_scan.py --timeframes Daily Weekly` — scan a subset of timeframes
  instead of all 5.
- `--out custom.json` — write somewhere else.

This writes:
- **`resultdow.json`** — Dow Theory swing structure + multi-level Fib
  entries, scanned across **all five timeframes** in one file (each row
  tagged with its `timeframe`).
- **`resultwgat.json`** — Wave-vs-Tide MACD alignment + EMA/RSI/ADX
  momentum & swing signals. This strategy is defined around Daily vs
  Weekly vs Monthly specifically, so it always reads `stockdata_D` /
  `stockdata_W` / `stockdata_M` regardless of what other timeframes
  exist.

Re-run either script any time your JSON data updates — each run simply
overwrites its result file.

## 4. View the dashboard

Browsers block `fetch()` of local JSON opened as a `file://` page, so
serve the **Root** folder over HTTP (not the `wgat` folder itself — the
dashboard's price-preview charts read sibling folders one level up, e.g.
`../stockdata_D/RELIANCE.json`):

```bash
cd Root
python -m http.server 8000
```

Then open **http://localhost:8000/wgat/** in your browser.

Two tabs:
- **DOW THEORY** — filter by timeframe, trend bucket, Fib entry type;
  click a row for Fib retracement levels + a mini price chart.
- **WGAT** — filter by Wave-vs-Tide category and Momentum/Swing signal;
  click a row for EMA13/50/100, RSI, ADX + a mini price chart.

Both tables are sortable (click a column header) and searchable by
symbol; the scrolling strip under the top bar shows live counts for the
current filtered view.

## 5. Demo data included

`resultdow.json` / `resultwgat.json` currently ship with output from
**synthetic placeholder data** (8 dummy symbols) purely so you can open
the dashboard immediately and see it working. Running `dow_scan.py` /
`wgat_scan.py` against your real `stockdata_*` JSON overwrites these
with real results. Because the placeholder run didn't sit next to real
`stockdata_*` folders, the sparkline charts in this demo won't have data
to draw from until you drop this folder into your real `Root/` — that's
expected and the dashboard shows a clear inline message instead of
breaking.

## 6. What changed from the earlier version

- `dow_scan.py` / `wgat_scan.py` are now **single files** — no more
  `common.py` / `indicators.py` imports.
- Input is **JSON**, not parquet — no `pyarrow` needed, no
  `parquet_to_json.py` conversion step.
- Folder names match your actual layout: `stockdata_15`, `stockdata_1H`,
  `stockdata_D`, `stockdata_W`, `stockdata_M` (no underscore after
  "stock").
- Output files are `resultdow.json` / `resultwgat.json`, written
  directly inside `wgat/` (no `data/` subfolder).
- `app.js` was updated only where it touches file paths (which files to
  fetch, and where sparkline source candles live); the HTML structure
  and CSS are untouched.
- All Dow Theory / Fib / MACD-alignment / EMA-RSI-ADX **logic is
  unchanged** — same swing detection, HH/HL/LH/LL labelling, trend
  bucket rules, Fib level + entry-zone math, and momentum/swing rules as
  the original Streamlit apps.
