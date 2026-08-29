/* =========================================================
   Master Scanner — dashboard logic
   Reads data/dow_results.json and data/wgat_results.json
   (produced by run_all.py) and renders two filterable,
   sortable tables with an expandable detail row per stock.
   ========================================================= */

const DATA = {
  dow: null,
  wgat: null,
};

const SORT = {
  dow: { key: "stock", dir: "asc" },
  wgat: { key: "stock", dir: "asc" },
};

const EXPANDED = { dow: new Set(), wgat: new Set() };

const TF_FOLDER = {
  "15 Min": "stock_data_15",
  "1 Hour": "stock_data_1H",
  "Daily": "stock_data_D",
  "Weekly": "stock_data_W",
  "Monthly": "stock_data_M",
};

const FIB_ORDER = ["23pct", "38pct", "50pct", "618pct", "78pct"];
const FIB_LABEL = { "23pct": "23%", "38pct": "38%", "50pct": "50%", "618pct": "61.8%", "78pct": "78%" };

/* --------------------------------------------------------
   BOOTSTRAP
   -------------------------------------------------------- */
document.addEventListener("DOMContentLoaded", init);

async function init() {
  wireTabs();
  wireFilters();
  wireSorting();

  try {
    const [dow, wgat] = await Promise.all([
      fetchJSON("data/dow_results.json"),
      fetchJSON("data/wgat_results.json"),
    ]);
    DATA.dow = dow;
    DATA.wgat = wgat;

    updateMeta(dow, wgat);
    renderTicker("dow");
    renderTable("dow");
    renderTable("wgat");
  } catch (err) {
    console.error(err);
    showFetchError(err);
  }
}

async function fetchJSON(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

function showFetchError(err) {
  const isFileProtocol = location.protocol === "file:";
  const msg = `
    <div class="icon">⚠</div>
    <h3>Couldn't load scan data</h3>
    <p>
      ${isFileProtocol
        ? "Browsers block <code>fetch()</code> of local JSON when a page is opened directly as a file. Serve this folder over HTTP instead:"
        : "The dashboard could not reach <code>data/dow_results.json</code> / <code>data/wgat_results.json</code>."}
    </p>
    ${isFileProtocol ? '<p><code>cd wgat && python -m http.server 8000</code><br>then open <code>http://localhost:8000</code></p>' : ""}
    <p style="color:var(--text-faint)">Also make sure you've run <code>python run_all.py --root .. --date YYYY-MM-DD</code> at least once to generate the JSON files.</p>
  `;
  ["dowState", "wgatState"].forEach(id => {
    const el = document.getElementById(id);
    el.innerHTML = msg;
    el.classList.remove("hidden");
  });
  document.getElementById("metaLive").textContent = "no data";
}

function updateMeta(dow, wgat) {
  document.getElementById("metaLive").textContent = "data loaded";
  const genAt = dow?.generated_at || wgat?.generated_at;
  const scanDate = dow?.scan_date || wgat?.scan_date;
  document.getElementById("metaDate").textContent =
    `Scan date: ${scanDate || "—"}  ·  generated ${genAt ? new Date(genAt).toLocaleString() : "—"}`;
}

/* --------------------------------------------------------
   TABS
   -------------------------------------------------------- */
function wireTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach(b => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");

      const tab = btn.dataset.tab;
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
      document.getElementById(`tab-${tab}`).classList.remove("hidden");
      renderTicker(tab);
    });
  });
}

/* --------------------------------------------------------
   FILTERS
   -------------------------------------------------------- */
function wireFilters() {
  ["dowTimeframe", "dowTrend", "dowFib", "dowSearch"].forEach(id =>
    document.getElementById(id).addEventListener("input", () => { renderTable("dow"); renderTicker("dow"); })
  );
  document.getElementById("dowReset").addEventListener("click", () => {
    document.getElementById("dowTimeframe").value = "Daily";
    document.getElementById("dowTrend").value = "All";
    document.getElementById("dowFib").value = "All";
    document.getElementById("dowSearch").value = "";
    renderTable("dow"); renderTicker("dow");
  });

  ["wgatCat1", "wgatCat2", "wgatSearch"].forEach(id =>
    document.getElementById(id).addEventListener("input", () => { renderTable("wgat"); renderTicker("wgat"); })
  );
  document.getElementById("wgatReset").addEventListener("click", () => {
    document.getElementById("wgatCat1").value = "All";
    document.getElementById("wgatCat2").value = "All";
    document.getElementById("wgatSearch").value = "";
    renderTable("wgat"); renderTicker("wgat");
  });
}

function getDowFiltered() {
  if (!DATA.dow) return [];
  const tf = document.getElementById("dowTimeframe").value;
  const trend = document.getElementById("dowTrend").value;
  const fib = document.getElementById("dowFib").value;
  const q = document.getElementById("dowSearch").value.trim().toUpperCase();

  return DATA.dow.results.filter(r => {
    if (tf !== "All" && r.timeframe !== tf) return false;
    if (trend !== "All" && r.trend_bucket !== trend) return false;
    if (fib !== "All" && r[fib] !== true) return false;
    if (q && !r.stock.toUpperCase().includes(q)) return false;
    return true;
  });
}

function getWgatFiltered() {
  if (!DATA.wgat) return [];
  const cat1 = document.getElementById("wgatCat1").value;
  const cat2 = document.getElementById("wgatCat2").value;
  const q = document.getElementById("wgatSearch").value.trim().toUpperCase();

  return DATA.wgat.results.filter(r => {
    if (cat1 !== "All" && r.category_1 !== cat1) return false;
    if (cat2 !== "All" && r[cat2] !== true) return false;
    if (q && !r.stock.toUpperCase().includes(q)) return false;
    return true;
  });
}

/* --------------------------------------------------------
   SORTING
   -------------------------------------------------------- */
function wireSorting() {
  document.querySelectorAll("#dowTable th.sortable").forEach(th =>
    th.addEventListener("click", () => toggleSort("dow", th))
  );
  document.querySelectorAll("#wgatTable th.sortable").forEach(th =>
    th.addEventListener("click", () => toggleSort("wgat", th))
  );
}

function toggleSort(scope, th) {
  const key = th.dataset.key;
  const s = SORT[scope];
  if (s.key === key) {
    s.dir = s.dir === "asc" ? "desc" : "asc";
  } else {
    s.key = key;
    s.dir = "asc";
  }
  renderTable(scope);
}

function applySort(rows, scope) {
  const { key, dir } = SORT[scope];
  const mult = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    let av = a[key], bv = b[key];
    if (av == null) av = dir === "asc" ? Infinity : -Infinity;
    if (bv == null) bv = dir === "asc" ? Infinity : -Infinity;
    if (typeof av === "string") return av.localeCompare(bv) * mult;
    return (av - bv) * mult;
  });
}

function updateSortHeaders(tableId, scope) {
  document.querySelectorAll(`#${tableId} th.sortable`).forEach(th => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.dataset.key === SORT[scope].key) {
      th.classList.add(SORT[scope].dir === "asc" ? "sorted-asc" : "sorted-desc");
    }
  });
}

/* --------------------------------------------------------
   RENDER: DOW TABLE
   -------------------------------------------------------- */
function trendBadgeClass(bucket) {
  if (bucket === "Uptrend" || bucket === "Reversal To Uptrend") return "bull";
  if (bucket === "Downtrend" || bucket === "Reversal To Downtrend") return "bear";
  return "neutral";
}

function renderTable(scope) {
  if (scope === "dow") return renderDow();
  return renderWgat();
}

function renderDow() {
  const body = document.getElementById("dowBody");
  const stateEl = document.getElementById("dowState");
  body.innerHTML = "";

  if (!DATA.dow) { stateEl.classList.remove("hidden"); stateEl.innerHTML = loadingState(); return; }

  let rows = getDowFiltered();
  rows = applySort(rows, "dow");
  updateSortHeaders("dowTable", "dow");
  document.getElementById("dowCount").innerHTML = `<b>${rows.length}</b> rows`;

  if (rows.length === 0) {
    stateEl.classList.remove("hidden");
    stateEl.innerHTML = emptyState("No stocks match these filters", "Try widening the timeframe or trend filter.");
    return;
  }
  stateEl.classList.add("hidden");

  const frag = document.createDocumentFragment();
  rows.forEach((r) => {
    const rowId = `${r.stock}__${r.timeframe}`;
    const tr = document.createElement("tr");
    tr.className = EXPANDED.dow.has(rowId) ? "expanded" : "";
    tr.innerHTML = `
      <td><div class="cell-stock"><span class="stock-ticker">${r.stock}</span></div></td>
      <td><span class="tf-tag">${r.timeframe}</span></td>
      <td><span class="badge ${trendBadgeClass(r.trend_bucket)}"><span class="stamp">${abbrevTrend(r.trend_bucket)}</span> ${r.trend_bucket}</span></td>
      <td class="mono strong">${fmtNum(r.last_close)}</td>
      <td>${fibChips(r, "bull")}</td>
      <td>${fibChips(r, "bear")}</td>
      <td class="mono">${fmtDate(r.last_date)}</td>
    `;
    tr.addEventListener("click", () => toggleExpand("dow", rowId));
    frag.appendChild(tr);

    if (EXPANDED.dow.has(rowId)) {
      frag.appendChild(buildDowExpandRow(r));
    }
  });
  body.appendChild(frag);
}

function abbrevTrend(bucket) {
  const map = {
    "Uptrend": "UP", "Downtrend": "DN",
    "Reversal To Uptrend": "REV\u2191", "Reversal To Downtrend": "REV\u2193",
    "Triangle / Sideways": "SIDE",
  };
  return map[bucket] || "\u2014";
}

function fibChips(r, side) {
  return `<div class="chipset">${FIB_ORDER.map(f => {
    const hitKey = `${f}_${side}`;
    const priceKey = `${f}_${side === "bull" ? "up" : "down"}`;
    const on = r[hitKey] === true;
    const price = r[priceKey];
    const title = price != null ? `${FIB_LABEL[f]} ${side === "bull" ? "retrace (up)" : "retrace (down)"} @ ${fmtNum(price)}` : `${FIB_LABEL[f]} \u2014 n/a`;
    return `<span class="chip-dot ${on ? "on " + side : ""}" title="${title}">${FIB_LABEL[f]}</span>`;
  }).join("")}</div>`;
}

function buildDowExpandRow(r) {
  const tr = document.createElement("tr");
  tr.className = "expand-row";
  const td = document.createElement("td");
  td.colSpan = 7;

  const fibRows = FIB_ORDER.map(f => {
    const up = r[`${f}_up`], down = r[`${f}_down`];
    return `<div class="kv-row"><span>${FIB_LABEL[f]}</span><span>${up != null ? "\u2191 " + fmtNum(up) : down != null ? "\u2193 " + fmtNum(down) : "\u2014"}</span></div>`;
  }).join("");

  td.innerHTML = `
    <div class="expand-inner">
      <div class="expand-col">
        <h4>Fib Retracement Levels</h4>
        <div class="kv-list">${fibRows}</div>
      </div>
      <div class="expand-col">
        <h4>Detail</h4>
        <div class="kv-list">
          <div class="kv-row"><span>Timeframe</span><span>${r.timeframe}</span></div>
          <div class="kv-row"><span>Trend bucket</span><span>${r.trend_bucket}</span></div>
          <div class="kv-row"><span>Last close</span><span>${fmtNum(r.last_close)}</span></div>
          <div class="kv-row"><span>Last candle</span><span>${fmtDate(r.last_date)}</span></div>
        </div>
      </div>
      <div class="expand-col spark-wrap">
        <h4>Price (last bars)</h4>
        <canvas class="spark-canvas" data-symbol="${r.stock}" data-tf="${r.timeframe}"></canvas>
      </div>
    </div>
  `;
  tr.appendChild(td);
  requestAnimationFrame(() => loadSparkline(td.querySelector(".spark-canvas")));
  return tr;
}

/* --------------------------------------------------------
   RENDER: WGAT TABLE
   -------------------------------------------------------- */
function wgatBadgeClass(cat) {
  if (cat.includes("Uptrend") || cat.includes("Aligned Up") || cat.includes("Going Up")) return "bull";
  if (cat.includes("Down") || cat.includes("Aligned Down")) return "bear";
  return "neutral";
}

function renderWgat() {
  const body = document.getElementById("wgatBody");
  const stateEl = document.getElementById("wgatState");
  body.innerHTML = "";

  if (!DATA.wgat) { stateEl.classList.remove("hidden"); stateEl.innerHTML = loadingState(); return; }

  let rows = getWgatFiltered();
  rows = applySort(rows, "wgat");
  updateSortHeaders("wgatTable", "wgat");
  document.getElementById("wgatCount").innerHTML = `<b>${rows.length}</b> rows`;

  if (rows.length === 0) {
    stateEl.classList.remove("hidden");
    stateEl.innerHTML = emptyState("No stocks match these filters", "Try widening the trend or signal filter.");
    return;
  }
  stateEl.classList.add("hidden");

  const frag = document.createDocumentFragment();
  rows.forEach(r => {
    const rowId = r.stock;
    const tr = document.createElement("tr");
    tr.className = EXPANDED.wgat.has(rowId) ? "expanded" : "";
    tr.innerHTML = `
      <td><div class="cell-stock"><span class="stock-ticker">${r.stock}</span></div></td>
      <td><span class="badge ${wgatBadgeClass(r.category_1)}">${r.category_1}</span></td>
      <td>${wgatSignals(r)}</td>
      <td class="mono strong">${fmtNum(r.last_close)}</td>
      <td class="mono ${rsiClass(r.rsi)}">${fmtNum(r.rsi)}</td>
      <td class="mono">${fmtNum(r.adx)}</td>
      <td class="mono">${fmtDate(r.last_date)}</td>
    `;
    tr.addEventListener("click", () => toggleExpand("wgat", rowId));
    frag.appendChild(tr);

    if (EXPANDED.wgat.has(rowId)) {
      frag.appendChild(buildWgatExpandRow(r));
    }
  });
  body.appendChild(frag);
}

function rsiClass(rsi) {
  if (rsi == null) return "";
  if (rsi >= 55) return "num-up";
  if (rsi <= 45) return "num-down";
  return "";
}

function wgatSignals(r) {
  const items = [
    ["BM", r.bullish_momentum, "bull", "Bullish Momentum"],
    ["bm", r.bearish_momentum, "bear", "Bearish Momentum"],
    ["BS", r.bullish_swing, "bull", "Bullish Swing"],
    ["bs", r.bearish_swing, "bear", "Bearish Swing"],
  ];
  return `<div class="chipset">${items.map(([lbl, on, cls, title]) =>
    `<span class="chip-dot ${on ? "on " + cls : ""}" title="${title}: ${on ? "yes" : "no"}">${lbl}</span>`
  ).join("")}</div>`;
}

function buildWgatExpandRow(r) {
  const tr = document.createElement("tr");
  tr.className = "expand-row";
  const td = document.createElement("td");
  td.colSpan = 7;
  td.innerHTML = `
    <div class="expand-inner">
      <div class="expand-col">
        <h4>Moving Averages</h4>
        <div class="kv-list">
          <div class="kv-row"><span>EMA 13</span><span>${fmtNum(r.ema13)}</span></div>
          <div class="kv-row"><span>EMA 50</span><span>${fmtNum(r.ema50)}</span></div>
          <div class="kv-row"><span>EMA 100</span><span>${fmtNum(r.ema100)}</span></div>
        </div>
      </div>
      <div class="expand-col">
        <h4>Momentum</h4>
        <div class="kv-list">
          <div class="kv-row"><span>RSI (14)</span><span>${fmtNum(r.rsi)}</span></div>
          <div class="kv-row"><span>ADX (14)</span><span>${fmtNum(r.adx)}</span></div>
          <div class="kv-row"><span>Last candle</span><span>${fmtDate(r.last_date)}</span></div>
        </div>
      </div>
      <div class="expand-col spark-wrap">
        <h4>Price (last bars, Daily)</h4>
        <canvas class="spark-canvas" data-symbol="${r.stock}" data-tf="Daily"></canvas>
      </div>
    </div>
  `;
  tr.appendChild(td);
  requestAnimationFrame(() => loadSparkline(td.querySelector(".spark-canvas")));
  return tr;
}

/* --------------------------------------------------------
   EXPAND / COLLAPSE
   -------------------------------------------------------- */
function toggleExpand(scope, rowId) {
  const set = EXPANDED[scope];
  if (set.has(rowId)) set.delete(rowId); else set.add(rowId);
  renderTable(scope);
}

/* --------------------------------------------------------
   SPARKLINE (reads data/raw/<timeframe_folder>/<symbol>.json)
   -------------------------------------------------------- */
async function loadSparkline(canvas) {
  if (!canvas) return;
  const symbol = canvas.dataset.symbol;
  const tf = canvas.dataset.tf;
  const folder = TF_FOLDER[tf];
  const wrap = canvas.parentElement;
  try {
    const bars = await fetchJSON(`data/raw/${folder}/${symbol}.json`);
    if (!bars || bars.length < 2) throw new Error("not enough bars");
    drawSparkline(canvas, bars);
  } catch (e) {
    wrap.innerHTML = `<h4>Price (last bars)</h4><div class="spark-empty">No raw OHLC JSON found for ${symbol} (${tf}). Run parquet_to_json.py to enable charts.</div>`;
  }
}

function drawSparkline(canvas, bars) {
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth || 260;
  const cssH = 90;
  canvas.width = cssW * dpr;
  canvas.height = cssH * dpr;
  canvas.style.height = cssH + "px";
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  const closes = bars.map(b => b.c);
  const min = Math.min(...closes), max = Math.max(...closes);
  const pad = 6;
  const w = cssW - pad * 2, h = cssH - pad * 2;

  const up = closes[closes.length - 1] >= closes[0];
  const lineColor = up ? "#2FBF71" : "#E8534F";
  const fillColor = up ? "rgba(47,191,113,0.12)" : "rgba(232,83,79,0.12)";

  const x = i => pad + (i / (closes.length - 1)) * w;
  const y = v => pad + h - ((v - min) / (max - min || 1)) * h;

  ctx.beginPath();
  closes.forEach((v, i) => i === 0 ? ctx.moveTo(x(i), y(v)) : ctx.lineTo(x(i), y(v)));
  ctx.lineTo(x(closes.length - 1), pad + h);
  ctx.lineTo(x(0), pad + h);
  ctx.closePath();
  ctx.fillStyle = fillColor;
  ctx.fill();

  ctx.beginPath();
  closes.forEach((v, i) => i === 0 ? ctx.moveTo(x(i), y(v)) : ctx.lineTo(x(i), y(v)));
  ctx.strokeStyle = lineColor;
  ctx.lineWidth = 1.6;
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(x(closes.length - 1), y(closes[closes.length - 1]), 2.6, 0, Math.PI * 2);
  ctx.fillStyle = lineColor;
  ctx.fill();
}

/* --------------------------------------------------------
   TICKER STRIP
   -------------------------------------------------------- */
function renderTicker(scope) {
  const track = document.getElementById("tickerTrack");
  let chips = [];

  if (scope === "dow" && DATA.dow) {
    const filtered = getDowFiltered();
    const rows = filtered.length ? filtered : DATA.dow.results;
    const counts = {};
    rows.forEach(r => { counts[r.trend_bucket] = (counts[r.trend_bucket] || 0) + 1; });
    chips = [
      chip("UPTREND", counts["Uptrend"] || 0, "bull"),
      chip("DOWNTREND", counts["Downtrend"] || 0, "bear"),
      chip("REV \u2192 UP", counts["Reversal To Uptrend"] || 0, "bull"),
      chip("REV \u2192 DOWN", counts["Reversal To Downtrend"] || 0, "bear"),
      chip("SIDEWAYS", counts["Triangle / Sideways"] || 0, "neutral"),
      chip("SCANNED", DATA.dow.results.length, "accent"),
    ];
  } else if (scope === "wgat" && DATA.wgat) {
    const rows = DATA.wgat.results;
    const bm = rows.filter(r => r.bullish_momentum).length;
    const bem = rows.filter(r => r.bearish_momentum).length;
    const bs = rows.filter(r => r.bullish_swing).length;
    const bes = rows.filter(r => r.bearish_swing).length;
    chips = [
      chip("BULL MOMENTUM", bm, "bull"),
      chip("BEAR MOMENTUM", bem, "bear"),
      chip("BULL SWING", bs, "bull"),
      chip("BEAR SWING", bes, "bear"),
      chip("SCANNED", rows.length, "accent"),
    ];
  } else {
    chips = [chip("LOADING", "\u2026", "neutral")];
  }

  const html = chips.map(chipHTML).join("");
  track.innerHTML = html + html; // duplicate for seamless marquee loop
}

function chip(label, val, cls) { return { label, val, cls }; }
function chipHTML(c) {
  return `<div class="ticker-chip ${c.cls}"><span class="lbl">${c.label}</span><span class="val">${c.val}</span></div>`;
}

/* --------------------------------------------------------
   FORMAT HELPERS
   -------------------------------------------------------- */
function fmtNum(v) {
  if (v == null || Number.isNaN(v)) return "\u2014";
  return Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtDate(v) {
  if (!v) return "\u2014";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return v;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}
function loadingState() {
  return `<div class="spinner"></div><h3>Loading scan data\u2026</h3>`;
}
function emptyState(title, sub) {
  return `<div class="icon">\u2205</div><h3>${title}</h3><p>${sub}</p>`;
}
