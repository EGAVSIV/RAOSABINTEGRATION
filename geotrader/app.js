/* =====================================================================
   GEOTRADER DASHBOARD — app.js
   Fetches output/result.json (written by engine.py) and renders the
   whole terminal. No build step, no framework — vanilla DOM + Chart.js
   for the two bar charts, hand-drawn <canvas> for the breadth gauge.
===================================================================== */

const RESULT_URL = "result.json";

const COLORS = {
  bull: "#35d68f",
  bear: "#ff5f6d",
  neutral: "#545e77",
  brass: "#d9a84e",
  ink1: "#b7c1d9",
  ink2: "#7c88a3",
  hull3: "#1a2233",
};

const state = {
  data: null,
  rsiFilters: { tf: new Set(), state: new Set() },
  sectorExplorerCount: 4,
};

/* ---------------------------------------------------------------- utils */
const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $all = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));
const fmtPct = (v) => `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};

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
  ["kpiStrip", "broaderList", "sectorList", "sectorExplorer", "terrainGrid",
    "momentumUp", "momentumDown", "rsiTableBody", "eventList"].forEach((id) => {
    const node = document.getElementById(id);
    if (node) node.innerHTML = msg;
  });
}

$("#refreshBtn").addEventListener("click", () => loadData());

/* ---------------------------------------------------------------- render root */
function renderAll(data) {
  renderTicker(data);
  renderKpis(data);
  renderChangeList("#broaderList", data.broader_market, "No broad indices mapped yet");
  renderChangeList("#sectorList", data.sector_performance, "No sector indices mapped yet");
  renderGauge(data.advance_decline);
  renderFnoChart(data.fno);
  renderSectorExplorer(data.sector_stocks);
  renderTerrain(data.sector_stocks);
  renderMomentum(data.momentum_streaks);
  renderRsiFilters(data.rsi_scanner);
  renderRsiTable(data.rsi_scanner);
  renderEvents(data.intraday_events);

  const gen = data.generated_at ? new Date(data.generated_at) : null;
  $("#generatedAt").textContent = gen
    ? `generated_at: ${gen.toLocaleString("en-IN")}`
    : "generated_at: —";
}

/* ---------------------------------------------------------------- ticker */
function renderTicker(data) {
  const track = $("#tickerTrack");
  const rows = [...(data.fno?.top5 || []), ...(data.fno?.bottom5 || [])];
  if (!rows.length) {
    track.innerHTML = `<span class="tick-item"><span class="sym">No F&amp;O data available</span></span>`;
    return;
  }
  const build = () => rows.map((r) => {
    const up = r.change >= 0;
    return `<span class="tick-item ${up ? "up" : "down"}">
      <span class="sym">${r.symbol}</span>
      <span class="arrow">${up ? "▲" : "▼"}</span>
      <span class="chg">${fmtPct(r.change)}</span>
    </span>`;
  }).join("");
  // duplicate content so the CSS -50% scroll loops seamlessly
  track.innerHTML = build() + build();
}

/* ---------------------------------------------------------------- KPI strip */
function renderKpis(data) {
  const fno = data.fno?.all || [];
  const best = data.fno?.top5?.[0];
  const worst = data.fno?.bottom5?.[0];
  const ad = data.advance_decline || { advance: 0, decline: 0, unchanged: 0 };
  const breadthPct = fno.length ? Math.round((ad.advance / fno.length) * 100) : 0;

  const cards = [
    {
      label: "F&O Universe", value: fno.length, sub: `${data.meta?.sectors_mapped ?? 0} sectors mapped`, cls: "",
    },
    {
      label: "Breadth (Advancing)", value: `${breadthPct}<small>%</small>`,
      sub: `${ad.advance} adv · ${ad.decline} dec · ${ad.unchanged} flat`,
      cls: breadthPct >= 50 ? "bull" : "bear",
    },
    {
      label: "Best Mover", value: best ? fmtPct(best.change) : "—",
      sub: best ? best.symbol : "no data", cls: "bull",
    },
    {
      label: "Worst Mover", value: worst ? fmtPct(worst.change) : "—",
      sub: worst ? worst.symbol : "no data", cls: "bear",
    },
  ];

  const strip = $("#kpiStrip");
  strip.innerHTML = "";
  cards.forEach((c) => {
    const panel = el("div", `panel kpi ${c.cls}`);
    panel.innerHTML = `
      <div class="label">${c.label}</div>
      <div class="value mono">${c.value}</div>
      <div class="sub">${c.sub}</div>`;
    strip.appendChild(panel);
  });
}

/* ---------------------------------------------------------------- change list rows */
function renderChangeList(sel, rows, emptyMsg) {
  const host = $(sel);
  host.innerHTML = "";
  if (!rows || !rows.length) {
    host.innerHTML = `<div class="empty-state"><div class="glyph">◌</div>${emptyMsg}</div>`;
    return;
  }
  const sorted = [...rows].sort((a, b) => b.change - a.change);
  const maxAbs = Math.max(...sorted.map((r) => Math.abs(r.change)), 0.01);

  sorted.forEach((r) => {
    const up = r.change >= 0;
    const pctWidth = clamp((Math.abs(r.change) / maxAbs) * 50, 0, 50);
    const row = el("div", "change-row");
    row.innerHTML = `
      <div class="sym">${r.symbol}</div>
      <div class="bar-track">
        <div class="zero"></div>
        <div class="bar-fill ${up ? "up" : "down"}" style="width:${pctWidth}%"></div>
      </div>
      <div class="chg ${up ? "up" : "down"}">${fmtPct(r.change)}</div>`;
    host.appendChild(row);
  });
}

/* ---------------------------------------------------------------- gauge (canvas) */
function renderGauge(ad) {
  const canvas = $("#gaugeCanvas");
  const ctx = canvas.getContext("2d");
  const { advance = 0, decline = 0, unchanged = 0 } = ad || {};
  const total = advance + decline + unchanged || 1;

  const cx = canvas.width / 2, cy = canvas.height / 2 + 6, r = 96, thickness = 22;
  const start = Math.PI, end = 2 * Math.PI; // semicircle, top half open downward look (bottom arc)

  ctx.clearRect(0, 0, canvas.width, canvas.height);

  const segs = [
    { v: advance, color: COLORS.bull },
    { v: decline, color: COLORS.bear },
    { v: unchanged, color: COLORS.neutral },
  ];

  let angle = start;
  segs.forEach((s) => {
    const sweep = (s.v / total) * Math.PI;
    if (sweep <= 0) return;
    ctx.beginPath();
    ctx.arc(cx, cy, r, angle, angle + sweep);
    ctx.lineWidth = thickness;
    ctx.strokeStyle = s.color;
    ctx.lineCap = "butt";
    ctx.stroke();
    angle += sweep;
  });

  // track underlay ticks
  ctx.save();
  ctx.globalAlpha = 0.25;
  ctx.beginPath();
  ctx.arc(cx, cy, r, start, end);
  ctx.lineWidth = 1;
  ctx.strokeStyle = COLORS.ink2;
  ctx.stroke();
  ctx.restore();

  // needle
  const breadth = advance / total; // 0..1
  const needleAngle = start + breadth * Math.PI;
  const nx = cx + Math.cos(needleAngle) * (r - thickness / 2 - 4);
  const ny = cy + Math.sin(needleAngle) * (r - thickness / 2 - 4);
  ctx.beginPath();
  ctx.moveTo(cx, cy);
  ctx.lineTo(nx, ny);
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = COLORS.brass;
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, Math.PI * 2);
  ctx.fillStyle = COLORS.brass;
  ctx.fill();

  // center readout
  ctx.fillStyle = "#eef2fb";
  ctx.textAlign = "center";
  ctx.font = "700 30px 'JetBrains Mono', monospace";
  ctx.fillText(`${Math.round(breadth * 100)}%`, cx, cy - 22);
  ctx.font = "500 11px 'Inter', sans-serif";
  ctx.fillStyle = COLORS.ink2;
  ctx.fillText("ADVANCING", cx, cy - 4);

  $("#advCount").textContent = advance;
  $("#decCount").textContent = decline;
  $("#unchCount").textContent = unchanged;
}

/* ---------------------------------------------------------------- hand-rolled SVG bar chart
   No external chart library — a small horizontal diverging-bar renderer that
   matches the design tokens exactly and has zero third-party dependencies. */
function renderHBarChart(hostEl, rows) {
  hostEl.innerHTML = "";
  if (!rows || !rows.length) {
    hostEl.innerHTML = `<div class="empty-state"><div class="glyph">◌</div>No data available</div>`;
    return;
  }
  const maxAbs = Math.max(...rows.map((r) => Math.abs(r.change)), 0.01);

  rows.forEach((r) => {
    const up = r.change >= 0;
    const pct = clamp((Math.abs(r.change) / maxAbs) * 50, 1.5, 50);
    const bar = el("div", "hbar-row");
    bar.innerHTML = `
      <div class="hbar-sym">${r.symbol}</div>
      <div class="hbar-track">
        <div class="hbar-zero"></div>
        <div class="hbar-fill ${up ? "up" : "down"}" style="width:${pct}%"></div>
      </div>
      <div class="hbar-val mono ${up ? "up" : "down"}">${fmtPct(r.change)}</div>`;
    hostEl.appendChild(bar);
  });
}

function renderFnoChart(fno) {
  const top5 = fno?.top5 || [];
  const bottom5 = fno?.bottom5 || [];
  const rows = [...top5].concat([...bottom5].reverse());
  renderHBarChart($("#fnoChart"), rows);
}

/* ---------------------------------------------------------------- sector explorer */
function renderSectorExplorer(sectorStocks) {
  const host = $("#sectorExplorer");
  host.innerHTML = "";
  const sectors = Object.keys(sectorStocks || {}).sort();

  if (!sectors.length) {
    host.innerHTML = `<div class="panel"><div class="empty-state"><div class="glyph">◌</div>No symbol_map.json sector mapping found</div></div>`;
    return;
  }

  for (let i = 0; i < state.sectorExplorerCount; i++) {
    const panel = el("div", "panel");
    const defaultSector = sectors[i % sectors.length];
    panel.innerHTML = `
      <div class="panel-head"><h2>Sector ${i + 1}</h2></div>
      <div class="select-shell" style="margin-bottom:14px">
        <select class="geo-select" data-slot="${i}"></select>
      </div>
      <div id="sectorChart${i}" class="hbar-chart"></div>`;
    host.appendChild(panel);

    const sel = panel.querySelector("select");
    sectors.forEach((s) => {
      const opt = el("option");
      opt.value = s;
      opt.textContent = s;
      if (s === defaultSector) opt.selected = true;
      sel.appendChild(opt);
    });
    sel.addEventListener("change", () => drawSectorChart(i, sel.value, sectorStocks));
    drawSectorChart(i, defaultSector, sectorStocks);
  }
}

function drawSectorChart(slot, sectorName, sectorStocks) {
  const info = sectorStocks[sectorName];
  const host = document.getElementById(`sectorChart${slot}`);
  if (!host) return;
  const rows = info ? [...(info.top5 || [])].concat([...(info.bottom5 || [])].reverse()) : [];
  renderHBarChart(host, rows);
}

/* ---------------------------------------------------------------- terrain heat grid */
function renderTerrain(sectorStocks) {
  const host = $("#terrainGrid");
  host.innerHTML = "";
  const entries = Object.entries(sectorStocks || {});
  if (!entries.length) {
    host.innerHTML = `<div class="empty-state"><div class="glyph">◌</div>No sector mapping available</div>`;
    return;
  }
  const maxAbs = Math.max(...entries.map(([, v]) => Math.abs(v.avg_change)), 0.01);

  entries
    .sort((a, b) => b[1].avg_change - a[1].avg_change)
    .forEach(([sector, info]) => {
      const t = info.avg_change;
      const intensity = clamp(Math.abs(t) / maxAbs, 0.12, 1);
      const bg = t >= 0
        ? `rgba(53, 214, 143, ${0.10 + 0.55 * intensity})`
        : `rgba(255, 95, 109, ${0.10 + 0.55 * intensity})`;
      const tile = el("div", "tile");
      tile.style.background = bg;
      tile.innerHTML = `
        <div class="t-name">${sector}</div>
        <div class="t-val mono">${fmtPct(t)}</div>
        <div class="t-sub">${info.count} stocks tracked</div>`;
      host.appendChild(tile);
    });
}

/* ---------------------------------------------------------------- momentum badges */
function renderMomentum(streaks) {
  const up = streaks?.up || [];
  const down = streaks?.down || [];
  const upHost = $("#momentumUp");
  const downHost = $("#momentumDown");

  const build = (rows, cls) => rows.map((r) => `
    <div class="badge ${cls}">
      <div class="b-sym">${r.symbol}</div>
      <div class="b-val mono">${r.strength}${cls === "up" ? "🔥" : "🧊"}</div>
    </div>`).join("");

  upHost.innerHTML = up.length ? build(up, "up") : `<div class="empty-state"><div class="glyph">◌</div>No stocks with an upside streak ≥ 2</div>`;
  downHost.innerHTML = down.length ? build(down, "down") : `<div class="empty-state"><div class="glyph">◌</div>No stocks with a downside streak ≥ 2</div>`;
}

/* ---------------------------------------------------------------- RSI scanner */
function renderRsiFilters(rows) {
  const tfs = [...new Set((rows || []).map((r) => r.tf))];
  const preferredOrder = ["15 MIN", "60 MIN", "DAY", "WEEK", "MONTH"];
  tfs.sort((a, b) => preferredOrder.indexOf(a) - preferredOrder.indexOf(b));
  const states = ["BULLISH", "CHANGE_NOW", "NEUTRAL", "BEARISH"];

  state.rsiFilters.tf = new Set(tfs);
  state.rsiFilters.state = new Set(states);

  const tfHost = $("#tfChips");
  tfHost.innerHTML = "";
  tfs.forEach((tf) => {
    const chip = el("span", "chip", tf);
    chip.dataset.active = "true";
    chip.addEventListener("click", () => {
      toggleFilter(state.rsiFilters.tf, tf, chip);
      renderRsiTable(state.data.rsi_scanner);
    });
    tfHost.appendChild(chip);
  });

  const stateHost = $("#stateChips");
  stateHost.innerHTML = "";
  states.forEach((s) => {
    const chip = el("span", "chip", s.replace("_", " "));
    chip.dataset.active = "true";
    chip.addEventListener("click", () => {
      toggleFilter(state.rsiFilters.state, s, chip);
      renderRsiTable(state.data.rsi_scanner);
    });
    stateHost.appendChild(chip);
  });
}

function toggleFilter(set, value, chipEl) {
  if (set.has(value)) {
    set.delete(value);
    chipEl.dataset.active = "false";
  } else {
    set.add(value);
    chipEl.dataset.active = "true";
  }
}

function renderRsiTable(rows) {
  const body = $("#rsiTableBody");
  body.innerHTML = "";
  const filtered = (rows || []).filter(
    (r) => state.rsiFilters.tf.has(r.tf) && state.rsiFilters.state.has(r.state)
  );
  $("#rsiCount").textContent = `${filtered.length} of ${rows?.length ?? 0} rows`;

  if (!filtered.length) {
    body.innerHTML = `<tr><td colspan="4"><div class="empty-state"><div class="glyph">◌</div>No symbols match the selected filters</div></td></tr>`;
    return;
  }

  filtered
    .sort((a, b) => b.rsi - a.rsi)
    .forEach((r) => {
      const tr = el("tr");
      const fillColor = r.rsi > 60 ? COLORS.bull : r.rsi < 40 ? COLORS.bear : COLORS.brass;
      tr.innerHTML = `
        <td class="mono" style="font-weight:600">${r.symbol}</td>
        <td class="mono dim">${r.tf}</td>
        <td>
          <div class="rsi-bar-cell">
            <div class="rsi-track"><div class="rsi-fill" style="width:${clamp(r.rsi, 0, 100)}%;background:${fillColor}"></div></div>
            <span class="mono" style="width:38px;display:inline-block">${r.rsi}</span>
          </div>
        </td>
        <td><span class="state-pill ${r.state}">${r.state.replace("_", " ")}</span></td>`;
      body.appendChild(tr);
    });
}

/* ---------------------------------------------------------------- intraday events */
function renderEvents(events) {
  const host = $("#eventList");
  host.innerHTML = "";
  if (!events || !events.length) {
    host.innerHTML = `<div class="empty-state"><div class="glyph">◌</div>No intraday breakout / breakdown events in the last 7 days</div>`;
    return;
  }
  events.forEach((ev) => {
    const ts = new Date(ev.ts);
    const tsLabel = ts.toLocaleString("en-IN", {
      day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata",
    });
    const card = el("div", `event-card ${ev.signal}`);
    card.innerHTML = `
      <div class="e-time">${tsLabel}</div>
      <div class="e-sym">${ev.symbol}</div>
      <div class="e-tf">${ev.tf}</div>
      <div class="e-signal">${ev.signal}</div>
      <div class="e-reasons">${(ev.reasons || []).map((r) => `<span>• ${r}</span>`).join("")}</div>`;
    host.appendChild(card);
  });
}

/* ---------------------------------------------------------------- boot */
loadData();
setInterval(() => loadData({ silent: true }), 5 * 60 * 1000); // auto-refresh every 5 min
