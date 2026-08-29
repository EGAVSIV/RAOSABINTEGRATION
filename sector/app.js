/* =====================================================================
   GEOTRADER SECTOR — app.js
   Fetches result.json (written by engine.py) and renders the whole
   sector-rotation terminal: performance bars, RRG quadrant plots (hand
   -rolled SVG, no chart library), rotation table, model portfolio and
   the sector-leader scanner.
===================================================================== */

const RESULT_URL = "result.json";

const COLORS = {
  bull: "#35d68f",
  bear: "#ff5f6d",
  brass: "#d9a84e",
  blue: "#4fb0ff",
  ink1: "#b7c1d9",
  ink2: "#7c88a3",
};

const QUAD_COLOR = {
  Leading: "#35d68f",
  Improving: "#4fb0ff",
  Lagging: "#ff5f6d",
  Weakening: "#d9a84e",
  Unknown: "#7c88a3",
};

const state = {
  data: null,
  lookback: "30",
};

/* ---------------------------------------------------------------- utils */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const fmtPct = (v) => (v === null || v === undefined) ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

/* ---------------------------------------------------------------- clock */
function tickClock() {
  const now = new Date();
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const hh = String(ist.getHours()).padStart(2, "0");
  const mm = String(ist.getMinutes()).padStart(2, "0");
  const ss = String(ist.getSeconds()).padStart(2, "0");
  $("#clockTime").textContent = `${hh}:${mm}:${ss}`;
  $("#clockDate").textContent = ist.toLocaleDateString("en-IN", {
    weekday: "short", day: "2-digit", month: "short", year: "numeric",
  }) + " IST";
}
setInterval(tickClock, 1000);
tickClock();

/* ---------------------------------------------------------------- fetch */
async function loadData({ silent = false } = {}) {
  const btn = $("#refreshBtn");
  const statusText = $("#dataStatusText");
  const statusDot = $("#dataStatus .dot");
  if (!silent) btn.classList.add("loading");
  statusText.textContent = "Loading…";

  try {
    const res = await fetch(`${RESULT_URL}?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.data = data;
    if (data.meta?.default_lookback) state.lookback = String(data.meta.default_lookback);
    renderAll(data);
    statusText.textContent = "Live";
    statusDot.style.background = COLORS.bull;
    statusDot.style.boxShadow = `0 0 8px 2px ${COLORS.bull}55`;
  } catch (err) {
    console.error("Failed to load result.json", err);
    statusText.textContent = "Data unavailable";
    statusDot.style.background = COLORS.bear;
    statusDot.style.boxShadow = `0 0 8px 2px ${COLORS.bear}55`;
    renderFetchError();
  } finally {
    btn.classList.remove("loading");
  }
}

function renderFetchError() {
  const msg = `
    <div class="empty-state">
      <div class="glyph">⚠</div>
      Could not load <span class="mono">result.json</span>.
      Run <span class="mono">python engine.py</span> and make sure this page is served over HTTP
      (not opened as a local file:// path).
    </div>`;
  ["kpiStrip", "perfChart", "sectorRrg", "rotationTableBody", "topSectors",
    "stockRrg", "portfolioChart", "scannerTableBody"].forEach((id) => {
    const node = document.getElementById(id);
    if (node) node.innerHTML = msg;
  });
}

$("#refreshBtn").addEventListener("click", () => loadData());

/* ---------------------------------------------------------------- render root */
function renderAll(data) {
  $("#anchorDate").textContent = data.meta?.anchor_date || "—";
  const gen = data.generated_at ? new Date(data.generated_at) : null;
  $("#generatedAt").textContent = gen ? `generated_at: ${gen.toLocaleString("en-IN")}` : "generated_at: —";

  renderAlerts(data.rotation_alerts);
  renderKpis(data);
  renderLookbackPicker(data);
  renderPerfChart(state.lookback);
  renderSectorRrg(data.rotation_table);
  renderRotationTable(data.rotation_table);
  renderTopSectors(data.top_sectors);
  renderStockRrgSelector(data.stock_rrg);
  renderPortfolioChart(data.model_portfolio);
  renderScannerTable(data.sector_scanner);
}

/* ---------------------------------------------------------------- alerts */
function renderAlerts(alerts) {
  const host = $("#alertBanner");
  if (!alerts || !alerts.length) {
    host.hidden = true;
    host.innerHTML = "";
    return;
  }
  host.hidden = false;
  host.innerHTML = `<div class="ab-title">🚨 Sector Rotation Change Alerts</div>` +
    alerts.map((a) => `<div class="ab-row"><b>${a.sector}</b>: ${a.from} → <b>${a.to}</b></div>`).join("");
}

/* ---------------------------------------------------------------- KPI strip */
function renderKpis(data) {
  const rot = data.rotation_table || [];
  const leading = rot.filter((r) => r.rotation === "Leading").length;
  const lagging = rot.filter((r) => r.rotation === "Lagging").length;
  const best = rot[0];
  const niftyRet = data.nifty_returns?.["21"] ?? data.nifty_returns?.[String(state.lookback)];
  const nifty1m = rot.length ? (best ? best.rs_vs_nifty !== null ? (best.r1m - best.rs_vs_nifty) : null : null) : null;

  const cards = [
    { label: "Sectors Tracked", value: rot.length, sub: `${data.meta?.stocks_loaded ?? 0} stocks loaded`, cls: "" },
    { label: "Leading / Lagging", value: `${leading}<small> / </small>${lagging}`, sub: "1M &amp; 3M both positive / negative", cls: "" },
    { label: "Top Sector (1M)", value: best ? fmtPct(best.r1m) : "—", sub: best ? best.sector : "no data", cls: "bull" },
    { label: "NIFTY 1M", value: nifty1m !== null && nifty1m !== undefined ? fmtPct(nifty1m) : "—", sub: "benchmark return", cls: "blue" },
  ];

  const strip = $("#kpiStrip");
  strip.innerHTML = "";
  cards.forEach((c) => {
    const panel = el("div", `panel kpi ${c.cls}`);
    panel.innerHTML = `<div class="label">${c.label}</div><div class="value mono">${c.value}</div><div class="sub">${c.sub}</div>`;
    strip.appendChild(panel);
  });
}

/* ---------------------------------------------------------------- lookback picker + performance chart */
function renderLookbackPicker(data) {
  const options = data.meta?.lookback_options || [10, 15, 20, 30, 45, 60];
  const host = $("#lookbackPicker");
  host.innerHTML = "";
  options.forEach((lb) => {
    const chip = el("span", "chip", `${lb}D`);
    chip.dataset.active = String(lb) === String(state.lookback);
    chip.addEventListener("click", () => {
      state.lookback = String(lb);
      $all_chips(host).forEach((c) => (c.dataset.active = "false"));
      chip.dataset.active = "true";
      renderPerfChart(state.lookback);
    });
    host.appendChild(chip);
  });
}
function $all_chips(host) { return Array.from(host.querySelectorAll(".chip")); }

function renderPerfChart(lookback) {
  const host = $("#perfChart");
  const data = state.data;
  const rows = data?.performance_table?.[lookback] || [];
  const niftyRet = data?.nifty_returns?.[lookback];
  host.innerHTML = "";

  if (!rows.length) {
    host.innerHTML = `<div class="empty-state"><div class="glyph">◌</div>No performance data for this lookback</div>`;
    return;
  }

  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.return)), Math.abs(niftyRet || 0), 0.01);

  rows.forEach((r) => {
    const up = r.status === "Outperforming";
    const barPct = clamp((Math.abs(r.return) / maxAbs) * 50, 1.5, 50);
    const niftyPos = clamp(50 + ((niftyRet || 0) / maxAbs) * 50, 0, 100);

    const row = el("div", "hbar-row-lg");
    row.innerHTML = `
      <div class="hbar-sym-lg">${r.symbol}</div>
      <div class="hbar-track-lg">
        <div class="hbar-zero-lg"></div>
        <div class="hbar-fill-lg ${r.return >= 0 ? "up" : "down"}" style="width:${barPct}%;${r.return >= 0 ? "" : ""}background:${up ? "linear-gradient(90deg,#1f8a5c,var(--bull))" : "linear-gradient(90deg,var(--bear),#b23a44)"}"></div>
        <div class="hbar-fill-lg nifty-marker" style="left:${niftyPos}%"></div>
      </div>
      <div class="hbar-val-lg ${r.return >= 0 ? "up" : "down"}">${fmtPct(r.return)}</div>`;
    host.appendChild(row);
  });

  const legend = el("div", "small dim", `<span style="color:var(--brass)">▍</span> NIFTY ${lookback}D return: <b class="mono">${fmtPct(niftyRet)}</b> — bar color = out/under-performance vs NIFTY`);
  legend.style.marginTop = "10px";
  host.appendChild(legend);
}

/* ---------------------------------------------------------------- RRG SVG quadrant plot */
function buildRrgSvg(points, { xKey, yKey, labelKey, xLabel, yLabel, colorFn }) {
  const W = 520, H = 520, PAD = 46;
  const plotW = W - PAD * 2, plotH = H - PAD * 2;

  if (!points.length) {
    return `<div class="empty-state"><div class="glyph">◌</div>No data to plot</div>`;
  }

  const xs = points.map((p) => p[xKey]);
  const ys = points.map((p) => p[yKey]);
  const xPad = Math.max(1, Math.max(...xs.map(Math.abs)) * 0.3);
  const yPad = Math.max(1, Math.max(...ys.map(Math.abs)) * 0.3);
  const xMin = Math.min(...xs) - xPad, xMax = Math.max(...xs) + xPad;
  const yMin = Math.min(...ys) - yPad, yMax = Math.max(...ys) + yPad;

  const sx = (v) => PAD + ((v - xMin) / (xMax - xMin)) * plotW;
  const sy = (v) => PAD + plotH - ((v - yMin) / (yMax - yMin)) * plotH;
  const zx = sx(0), zy = sy(0);

  const quadRects = `
    <rect x="${zx}" y="${PAD}" width="${PAD + plotW - zx}" height="${zy - PAD}" fill="${QUAD_COLOR.Leading}" opacity="0.10"></rect>
    <rect x="${PAD}" y="${PAD}" width="${zx - PAD}" height="${zy - PAD}" fill="${QUAD_COLOR.Improving}" opacity="0.10"></rect>
    <rect x="${PAD}" y="${zy}" width="${zx - PAD}" height="${PAD + plotH - zy}" fill="${QUAD_COLOR.Lagging}" opacity="0.10"></rect>
    <rect x="${zx}" y="${zy}" width="${PAD + plotW - zx}" height="${PAD + plotH - zy}" fill="${QUAD_COLOR.Weakening}" opacity="0.10"></rect>`;

  const quadLabels = `
    <text x="${W - PAD - 6}" y="${PAD + 16}" text-anchor="end" class="rrg-quad-label" fill="${QUAD_COLOR.Leading}">LEADING</text>
    <text x="${PAD + 6}" y="${PAD + 16}" class="rrg-quad-label" fill="${QUAD_COLOR.Improving}">IMPROVING</text>
    <text x="${PAD + 6}" y="${H - PAD - 8}" class="rrg-quad-label" fill="${QUAD_COLOR.Lagging}">LAGGING</text>
    <text x="${W - PAD - 6}" y="${H - PAD - 8}" text-anchor="end" class="rrg-quad-label" fill="${QUAD_COLOR.Weakening}">WEAKENING</text>`;

  const axisLines = `
    <line x1="${PAD}" y1="${zy}" x2="${W - PAD}" y2="${zy}" stroke="rgba(140,160,200,0.3)" stroke-dasharray="4 4"></line>
    <line x1="${zx}" y1="${PAD}" x2="${zx}" y2="${H - PAD}" stroke="rgba(140,160,200,0.3)" stroke-dasharray="4 4"></line>`;

  const gridBorder = `<rect x="${PAD}" y="${PAD}" width="${plotW}" height="${plotH}" fill="none" stroke="rgba(140,160,200,0.2)"></rect>`;

  const pts = points.map((p) => {
    const cx = sx(p[xKey]), cy = sy(p[yKey]);
    const color = colorFn ? colorFn(p) : COLORS.blue;
    return `<g class="rrg-point">
      <circle cx="${cx}" cy="${cy}" r="6" fill="${color}" fill-opacity="0.85" stroke="#080b12" stroke-width="1.5"></circle>
      <text x="${cx + 8}" y="${cy - 8}">${p[labelKey]}</text>
    </g>`;
  }).join("");

  const axisLabels = `
    <text x="${W / 2}" y="${H - 10}" text-anchor="middle" class="rrg-axis-label">${xLabel}</text>
    <text x="14" y="${H / 2}" text-anchor="middle" class="rrg-axis-label" transform="rotate(-90 14 ${H / 2})">${yLabel}</text>`;

  return `<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">
    ${quadRects}${gridBorder}${axisLines}${quadLabels}${pts}${axisLabels}
  </svg>`;
}

function renderSectorRrg(rotationTable) {
  const host = $("#sectorRrg");
  const points = (rotationTable || []).filter((r) => r.rs_vs_nifty !== null && r.momentum !== null);
  host.innerHTML = buildRrgSvg(points, {
    xKey: "rs_vs_nifty", yKey: "momentum", labelKey: "sector",
    xLabel: "Relative Strength vs NIFTY (1M %)", yLabel: "Momentum (1M − 3M)",
    colorFn: (p) => QUAD_COLOR[p.rotation] || COLORS.blue,
  });
}

/* ---------------------------------------------------------------- rotation table */
function renderRotationTable(rows) {
  const body = $("#rotationTableBody");
  body.innerHTML = "";
  if (!rows || !rows.length) {
    body.innerHTML = `<tr><td colspan="6"><div class="empty-state"><div class="glyph">◌</div>No rotation data available</div></td></tr>`;
    return;
  }
  rows.forEach((r) => {
    const tr = el("tr");
    const cls = (v) => (v >= 0 ? "up-txt" : "down-txt");
    tr.innerHTML = `
      <td>${r.rs_rank}</td>
      <td style="font-weight:700;color:var(--ink-0)">${r.sector}</td>
      <td class="${cls(r.r1m)}">${fmtPct(r.r1m)}</td>
      <td class="${cls(r.r3m)}">${fmtPct(r.r3m)}</td>
      <td class="${r.r6m !== null ? cls(r.r6m) : "dim"}">${fmtPct(r.r6m)}</td>
      <td><span class="rotation-pill ${r.rotation}">${r.rotation}</span></td>`;
    body.appendChild(tr);
  });
}

/* ---------------------------------------------------------------- top sectors */
function renderTopSectors(top) {
  const host = $("#topSectors");
  host.innerHTML = "";
  if (!top || !top.length) {
    host.innerHTML = `<div class="empty-state"><div class="glyph">◌</div>No data</div>`;
    return;
  }
  top.forEach((r, i) => {
    const card = el("div", "top-sector-card");
    card.innerHTML = `
      <div class="ts-rank mono">#${i + 1}</div>
      <div class="ts-name">${r.sector}</div>
      <div class="ts-val mono ${r.r1m >= 0 ? "up" : "down"}">${fmtPct(r.r1m)}</div>
      <div class="ts-sub"><span class="rotation-pill ${r.rotation}">${r.rotation}</span></div>`;
    host.appendChild(card);
  });
}

/* ---------------------------------------------------------------- stock-level RRG */
function renderStockRrgSelector(stockRrg) {
  const selectShell = $("#stockRrgSelectShell");
  const sel = $("#stockRrgSelect");
  const sectors = Object.keys(stockRrg || {}).sort();

  if (!sectors.length) {
    selectShell.style.display = "none";
    $("#stockRrg").innerHTML = `<div class="empty-state"><div class="glyph">◌</div>No stock-level data available — check sector_stocks.json and stockdata_D coverage</div>`;
    $("#stockRrgAsOf").textContent = "";
    return;
  }
  selectShell.style.display = "";
  sel.innerHTML = "";
  sectors.forEach((s) => {
    const opt = el("option");
    opt.value = s; opt.textContent = s;
    sel.appendChild(opt);
  });
  sel.addEventListener("change", () => drawStockRrg(sel.value, stockRrg));
  drawStockRrg(sectors[0], stockRrg);
}

function drawStockRrg(sector, stockRrg) {
  const info = stockRrg[sector];
  const host = $("#stockRrg");
  const asOf = $("#stockRrgAsOf");
  if (!info || !info.points?.length) {
    host.innerHTML = `<div class="empty-state"><div class="glyph">◌</div>No stock data for ${sector}</div>`;
    asOf.textContent = "";
    return;
  }
  host.innerHTML = buildRrgSvg(info.points, {
    xKey: "rs_vs_sector", yKey: "momentum", labelKey: "symbol",
    xLabel: `Relative Strength vs ${sector} (1M %)`, yLabel: "Momentum (1M − 3M)",
    colorFn: (p) => (p.rs_vs_sector >= 0 && p.momentum >= 0 ? QUAD_COLOR.Leading
      : p.rs_vs_sector < 0 && p.momentum >= 0 ? QUAD_COLOR.Improving
      : p.rs_vs_sector < 0 && p.momentum < 0 ? QUAD_COLOR.Lagging
      : QUAD_COLOR.Weakening),
  });
  asOf.textContent = info.as_of ? `Stock data as of ${info.as_of} · sector 1M return: ${fmtPct(info.sector_1m)}` : "";
}

/* ---------------------------------------------------------------- model portfolio */
function renderPortfolioChart(rows) {
  const host = $("#portfolioChart");
  host.innerHTML = "";
  if (!rows || !rows.length) {
    host.innerHTML = `<div class="empty-state"><div class="glyph">◌</div>No sectors currently in Leading/Improving rotation</div>`;
    return;
  }
  const maxW = Math.max(...rows.map((r) => r.weight_pct), 0.01);
  rows.forEach((r) => {
    const pct = clamp((r.weight_pct / maxW) * 100, 2, 100);
    const row = el("div", "hbar-row-lg");
    row.innerHTML = `
      <div class="hbar-sym-lg">${r.sector}</div>
      <div class="hbar-track-lg">
        <div class="hbar-fill-lg up" style="left:0;width:${pct}%;background:linear-gradient(90deg,${QUAD_COLOR[r.rotation]},${QUAD_COLOR[r.rotation]}aa)"></div>
      </div>
      <div class="hbar-val-lg mono">${r.weight_pct}%</div>`;
    host.appendChild(row);
  });
}

/* ---------------------------------------------------------------- scanner table */
function renderScannerTable(rows) {
  const body = $("#scannerTableBody");
  body.innerHTML = "";
  if (!rows || !rows.length) {
    body.innerHTML = `<tr><td colspan="5"><div class="empty-state"><div class="glyph">◌</div>No sector-leading stocks detected</div></td></tr>`;
    return;
  }
  rows.forEach((r) => {
    const edge = r.stock_1m - r.sector_1m;
    const tr = el("tr");
    tr.innerHTML = `
      <td style="font-weight:700;color:var(--ink-0)">${r.sector}</td>
      <td>${r.stock}</td>
      <td class="${r.stock_1m >= 0 ? "up-txt" : "down-txt"}">${fmtPct(r.stock_1m)}</td>
      <td>${fmtPct(r.sector_1m)}</td>
      <td class="up-txt">+${edge.toFixed(2)}%</td>`;
    body.appendChild(tr);
  });
}

/* ---------------------------------------------------------------- boot */
loadData();
setInterval(() => loadData({ silent: true }), 5 * 60 * 1000);
