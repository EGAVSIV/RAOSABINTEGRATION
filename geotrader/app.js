/* ============================================================
   GEOTRADER — Market Radar dashboard logic
   Reads result.json, renders charts + custom widgets.
   ============================================================ */

const COLOR = {
  green: '#39F2A0', greenDim: 'rgba(57,242,160,0.12)',
  red: '#FF5D6C', redDim: 'rgba(255,93,108,0.12)',
  amber: '#F2A93B', amberDim: 'rgba(242,169,59,0.12)',
  cyan: '#4FD3F0',
  grid: 'rgba(43,54,70,0.5)',
  text: '#8FA0B5'
};

Chart.defaults.font.family = "'IBM Plex Mono', monospace";
Chart.defaults.font.size = 11;
Chart.defaults.color = COLOR.text;

let charts = {};
function destroy(id){ if(charts[id]){ charts[id].destroy(); delete charts[id]; } }

function fmtChange(v){ return (v>0?'+':'') + v.toFixed(2) + '%'; }
function colorFor(v){ return v>=0 ? COLOR.green : COLOR.red; }
function clamp(v,a,b){ return Math.max(a, Math.min(b,v)); }

// ---------------------------------------------------------------
// Animated counters
// ---------------------------------------------------------------
function animateCount(el, target, decimals=0){
  const start = 0;
  const dur = 700;
  const t0 = performance.now();
  function step(t){
    const p = clamp((t - t0) / dur, 0, 1);
    const eased = 1 - Math.pow(1-p, 3);
    const val = start + (target - start) * eased;
    el.textContent = decimals ? val.toFixed(decimals) : Math.round(val);
    if(p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// ---------------------------------------------------------------
// Inline SVG sparkline (no chart.js overhead for tiny trend lines)
// ---------------------------------------------------------------
function sparklineSVG(values, opts={}){
  if(!values || values.length < 2) return '<svg></svg>';
  const w = opts.w || 100, h = opts.h || 28, pad = 2;
  const min = Math.min(...values), max = Math.max(...values);
  const range = (max - min) || 1;
  const up = values[values.length-1] >= values[0];
  const stroke = opts.color || (up ? COLOR.green : COLOR.red);
  const stepX = (w - pad*2) / (values.length - 1);
  const pts = values.map((v,i) => {
    const x = pad + i*stepX;
    const y = pad + (h - pad*2) * (1 - (v-min)/range);
    return [x,y];
  });
  const line = pts.map(p=>p.join(',')).join(' ');
  const areaPath = `M${pts[0][0]},${h} L` + line.split(' ').join(' L') + ` L${pts[pts.length-1][0]},${h} Z`;
  const gradId = 'g' + Math.random().toString(36).slice(2,9);
  return `<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}" preserveAspectRatio="none">
    <defs><linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${stroke}" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="${stroke}" stop-opacity="0"/>
    </linearGradient></defs>
    <path d="${areaPath}" fill="url(#${gradId})" stroke="none"/>
    <polyline points="${line}" fill="none" stroke="${stroke}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;
}

// ---------------------------------------------------------------
// Horizontal bar chart (Chart.js) for movers panels
// ---------------------------------------------------------------
function horizontalBar(canvasId, rows, opts={}){
  destroy(canvasId);
  const canvas = document.getElementById(canvasId);
  if(!canvas) return;
  const ctx = canvas.getContext('2d');
  const labels = rows.map(r=>r.symbol);
  const data = rows.map(r=>r.change);
  charts[canvasId] = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets: [{ data, backgroundColor: data.map(colorFor), borderRadius: 4, barThickness: opts.thick || 14 }] },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio:false,
      plugins:{
        legend:{display:false},
        tooltip:{
          backgroundColor:'#0F141C', borderColor:'#2B3646', borderWidth:1, padding:10,
          titleFont:{family:"'Space Grotesk'", weight:600},
          bodyFont:{family:"'IBM Plex Mono'"},
          callbacks:{ label: c => fmtChange(c.raw) }
        }
      },
      scales:{
        x:{ grid:{color:COLOR.grid}, ticks:{callback:v=>v+'%'}, border:{display:false} },
        y:{ grid:{display:false}, ticks:{ autoSkip:false }, border:{display:false} }
      }
    }
  });
}

// ---------------------------------------------------------------
// Sections
// ---------------------------------------------------------------
function renderKPIs(d){
  animateCount(document.getElementById('kpiTotal'), d.meta.total_symbols);
  animateCount(document.getElementById('kpiAdv'), d.advance_decline.advance);
  animateCount(document.getElementById('kpiDec'), d.advance_decline.decline);
  animateCount(document.getElementById('kpiEvents'), d.intraday_events.length);

  const gt = new Date(d.generated_at);
  document.getElementById('genTime').textContent = isNaN(gt) ? d.generated_at : gt.toLocaleString();

  // mini sparkline of overall FNO universe change distribution (sorted) as a pulse
  const all = (d.fno.all||[]).map(r=>r.change).sort((a,b)=>a-b);
  document.getElementById('kpiSpark').innerHTML = all.length ? sparklineSVG(all, {color: COLOR.amber, h:30}) : '';
}

function renderTicker(d){
  const track = document.getElementById('tickerTrack');
  const top = d.fno.top5 || [], bottom = d.fno.bottom5 || [];
  const all = [...top, ...bottom];
  if(!all.length){ track.innerHTML = '<span class="tick">No FNO data available yet — run engine.py</span>'; return; }
  const html = all.map(r => `<span class="tick ${r.change>=0?'up':'down'}">${r.change>=0?'▲':'▼'} <span class="sym">${r.symbol}</span> ${fmtChange(r.change)}</span>`).join('');
  track.innerHTML = html + html;
}

function renderMoverList(containerId, rows){
  const el = document.getElementById(containerId);
  if(!rows || !rows.length){ el.innerHTML = '<div class="empty"><span class="glyph">◌</span>No symbols mapped for this panel</div>'; return; }
  el.innerHTML = rows.map(r => {
    const up = r.change >= 0;
    return `<div class="mover-row">
      <span class="sym">${r.symbol}</span>
      <span class="mover-spark">${sparklineSVG(r.spark, {color: up?COLOR.green:COLOR.red})}</span>
      <span class="price">${r.price ?? '—'}</span>
      <span class="chg ${up?'up':'down'}">${fmtChange(r.change)}</span>
    </div>`;
  }).join('');
}

// ---- Radial advance/decline gauge (signature element) ----
function renderGauge(d){
  const ad = d.advance_decline;
  const total = Math.max(1, ad.advance + ad.decline + ad.unchanged);
  const r = 70, cx = 85, cy = 85, circ = 2*Math.PI*r;

  const advFrac = ad.advance/total, decFrac = ad.decline/total, unchFrac = ad.unchanged/total;
  const advLen = circ*advFrac, decLen = circ*decFrac, unchLen = circ*unchFrac;

  const svg = document.getElementById('adGauge');
  svg.innerHTML = `
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#1A2230" stroke-width="14"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${COLOR.green}" stroke-width="14"
      stroke-dasharray="${advLen} ${circ-advLen}" stroke-linecap="round"
      style="filter:drop-shadow(0 0 5px ${COLOR.green}66)"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${COLOR.red}" stroke-width="14"
      stroke-dasharray="${decLen} ${circ-decLen}" stroke-dashoffset="${-advLen}" stroke-linecap="round"
      style="filter:drop-shadow(0 0 5px ${COLOR.red}66)"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#4A5A70" stroke-width="14"
      stroke-dasharray="${unchLen} ${circ-unchLen}" stroke-dashoffset="${-(advLen+decLen)}" stroke-linecap="round"/>
  `;
  document.querySelector('#gaugeCenter .n').textContent = total;
  document.getElementById('gAdv').textContent = ad.advance;
  document.getElementById('gDec').textContent = ad.decline;
  document.getElementById('gUnch').textContent = ad.unchanged;
}

function renderMomentum(d){
  const upEl = document.getElementById('momUp'), downEl = document.getElementById('momDown');
  const up = d.momentum_streaks.up||[], down = d.momentum_streaks.down||[];
  upEl.innerHTML = up.length ? up.map(r=>`<div class="badge up"><span class="flame">🔥</span>${r.symbol} <span class="n">${r.strength}d streak</span></div>`).join('') : '<div class="empty">No upside streaks ≥ 2 days</div>';
  downEl.innerHTML = down.length ? down.map(r=>`<div class="badge down"><span class="flame">🧊</span>${r.symbol} <span class="n">${r.strength}d streak</span></div>`).join('') : '<div class="empty">No downside streaks ≥ 2 days</div>';
}

// ---- Sector heat-tiles ----
const SECTOR_PALETTE_STOPS = [
  [-3, '#7A1F2B'], [-1, '#5C1E28'], [0, '#2B3646'], [1, '#0F5C3E'], [3, '#0E7A50']
];
function sectorColor(v){
  const stops = SECTOR_PALETTE_STOPS;
  if(v <= stops[0][0]) return stops[0][1];
  if(v >= stops[stops.length-1][0]) return stops[stops.length-1][1];
  for(let i=0;i<stops.length-1;i++){
    const [v0,c0] = stops[i], [v1,c1] = stops[i+1];
    if(v>=v0 && v<=v1){
      const t=(v-v0)/(v1-v0);
      return lerpColor(c0,c1,t);
    }
  }
  return '#2B3646';
}
function lerpColor(a,b,t){
  const pa=[1,3,5].map(i=>parseInt(a.slice(i,i+2),16));
  const pb=[1,3,5].map(i=>parseInt(b.slice(i,i+2),16));
  const p=pa.map((v,i)=>Math.round(v+(pb[i]-v)*t));
  return '#'+p.map(v=>v.toString(16).padStart(2,'0')).join('');
}

function renderSectorMap(d){
  const el = document.getElementById('sectorMap');
  const sectors = d.sector_stocks || {};
  const names = Object.keys(sectors);
  if(!names.length){ el.innerHTML = '<div class="empty"><span class="glyph">◌</span>No sector → stock mapping found in symbol_map.json</div>'; return; }
  el.innerHTML = names.map(name => {
    const g = sectors[name];
    const rows = [...(g.top5||[]), ...(g.bottom5||[])];
    const avg = rows.length ? rows.reduce((s,r)=>s+r.change,0)/rows.length : 0;
    const count = new Set(rows.map(r=>r.symbol)).size;
    return `<div class="sector-tile" style="background:${sectorColor(avg)}" title="${name}: ${fmtChange(avg)} avg">
      <div class="sec-name">${name}</div>
      <div class="sec-chg">${fmtChange(avg)}</div>
      <div class="sec-count">${count} symbols</div>
    </div>`;
  }).join('');
}

function renderSectorExplorer(d){
  const select = document.getElementById('sectorSelect');
  const sectors = Object.keys(d.sector_stocks||{});
  if(!sectors.length){
    select.style.display='none';
    document.getElementById('chartSectorStocks').parentElement.innerHTML = '<div class="empty"><span class="glyph">◌</span>No sector data to explore</div>';
    return;
  }
  select.innerHTML = sectors.map(s=>`<option value="${s}">${s}</option>`).join('');
  const draw = () => {
    const sec = select.value;
    const g = d.sector_stocks[sec];
    const rows = [...(g.bottom5||[]), ...(g.top5||[])].sort((a,b)=>a.change-b.change);
    horizontalBar('chartSectorStocks', rows, {thick:14});
  };
  select.onchange = draw;
  draw();
}

// ---- RSI heatmap matrix ----
function rsiHeatColor(v){
  if(v===null || v===undefined) return null;
  if(v>=70) return '#0E7A50';
  if(v>=60) return '#1F9E68';
  if(v>=50) return '#3E7A5E';
  if(v>=40) return '#6B5A3E';
  if(v>=30) return '#8A3E3E';
  return '#7A1F2B';
}
function renderRSIHeatmap(d){
  const el = document.getElementById('rsiHeatmap');
  const mat = d.rsi_matrix;
  if(!mat || !Object.keys(mat.rows||{}).length){
    el.innerHTML = '<div class="empty"><span class="glyph">◌</span>Not enough RSI data for a heatmap yet</div>';
    return;
  }
  const tfs = mat.timeframes;
  const symbols = Object.keys(mat.rows);
  const cols = `120px repeat(${tfs.length}, 1fr)`;
  let html = `<div class="heatmap-row" style="grid-template-columns:${cols};">
    <div></div>${tfs.map(tf=>`<div class="heatmap-head">${tf}</div>`).join('')}
  </div>`;
  symbols.forEach(sym => {
    const row = mat.rows[sym];
    html += `<div class="heatmap-row" style="grid-template-columns:${cols};">
      <div class="heatmap-sym">${sym}</div>
      ${tfs.map(tf => {
        const v = row[tf];
        if(v===undefined || v===null) return `<div class="heat-cell na">–</div>`;
        return `<div class="heat-cell" style="background:${rsiHeatColor(v)}">${v.toFixed(0)}</div>`;
      }).join('')}
    </div>`;
  });
  el.innerHTML = html;
  el.style.display = 'grid';
  el.style.gap = '4px';
}

// ---- RSI scanner table ----
function renderRSITable(d){
  const rows = d.rsi_scanner||[];
  const tfs = [...new Set(rows.map(r=>r.tf))];
  const states = ['BULLISH','CHANGE_NOW','NEUTRAL','BEARISH'];
  const filtersEl = document.getElementById('rsiFilters');
  const active = { tf: new Set(tfs), state: new Set(states) };

  function group(list, key, title){
    const box = document.createElement('div'); box.className='grp';
    const span = document.createElement('span'); span.textContent = title; box.appendChild(span);
    const opts = document.createElement('div'); opts.className = 'opts';
    list.forEach(v=>{
      const lbl = document.createElement('label');
      const cb = document.createElement('input'); cb.type='checkbox'; cb.checked=true;
      cb.addEventListener('change', ()=>{
        if(cb.checked) active[key].add(v); else active[key].delete(v);
        draw();
      });
      lbl.appendChild(cb); lbl.appendChild(document.createTextNode(v.replace('_',' ')));
      opts.appendChild(lbl);
    });
    box.appendChild(opts);
    return box;
  }
  filtersEl.innerHTML = '';
  if(!rows.length){
    document.querySelector('#rsiTable tbody').innerHTML = '<tr><td colspan="4" class="empty"><span class="glyph">◌</span>No RSI data available</td></tr>';
    return;
  }
  filtersEl.appendChild(group(tfs, 'tf', 'TIMEFRAME'));
  filtersEl.appendChild(group(states, 'state', 'STATE'));

  const tbody = document.querySelector('#rsiTable tbody');
  function rsiBarColor(v){
    if(v>=60) return COLOR.green;
    if(v<=40) return COLOR.red;
    return COLOR.amber;
  }
  function draw(){
    const filtered = rows.filter(r => active.tf.has(r.tf) && active.state.has(r.state));
    if(!filtered.length){ tbody.innerHTML = '<tr><td colspan="4" class="empty">No rows match the selected filters</td></tr>'; return; }
    tbody.innerHTML = filtered.map(r => `<tr>
      <td>${r.symbol}</td>
      <td>${r.tf}</td>
      <td><div class="rsi-bar-cell">
            <span>${r.rsi}</span>
            <div class="rsi-bar-track"><div class="rsi-bar-fill" style="width:${clamp(r.rsi,0,100)}%; background:${rsiBarColor(r.rsi)};"></div></div>
          </div></td>
      <td><span class="state-chip state-${r.state}">${r.state.replace('_',' ')}</span></td>
    </tr>`).join('');
  }
  draw();
}

function renderEvents(d){
  const el = document.getElementById('eventsList');
  const events = d.intraday_events||[];
  if(!events.length){ el.innerHTML = '<div class="empty"><span class="glyph">◌</span>No intraday breakout events in the last 7 days</div>'; return; }
  el.innerHTML = events.map(ev => {
    const ts = new Date(ev.ts);
    const tsStr = isNaN(ts) ? ev.ts : ts.toLocaleString();
    return `<div class="event ${ev.signal}">
      <div class="head">
        <span class="sig">${ev.signal}</span>
        <span class="sym">${ev.symbol}</span>
        <span class="tfbadge">${ev.tf}</span>
        <span class="ts">${tsStr}</span>
      </div>
      <div class="reasons">${(ev.reasons||[]).map(r=>'• '+r).join('<br>')}</div>
    </div>`;
  }).join('');
}

// ---------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------
function renderAll(d){
  renderKPIs(d);
  renderTicker(d);
  renderGauge(d);
  renderMoverList('broaderList', (d.broader_market||[]).slice().sort((a,b)=>b.change-a.change));
  renderMoverList('sectorIdxList', (d.sector_performance||[]).slice().sort((a,b)=>b.change-a.change));
  const fnoRows = [...(d.fno.top5||[]), ...(d.fno.bottom5||[])];
  horizontalBar('chartFno', fnoRows.sort((a,b)=>a.change-b.change), {thick:16});
  renderSectorMap(d);
  renderSectorExplorer(d);
  renderMomentum(d);
  renderRSIHeatmap(d);
  renderRSITable(d);
  renderEvents(d);
}

async function loadResult(){
  const btn = document.getElementById('refreshBtn');
  btn.classList.add('loading');
  try{
    const res = await fetch('geotrader/result.json?_=' + Date.now());
    if(!res.ok) throw new Error('HTTP ' + res.status);
    const data = await res.json();
    renderAll(data);
    const banner = document.getElementById('errBanner');
    if(banner) banner.remove();
  }catch(err){
    const wrap = document.querySelector('.wrap');
    const existing = document.getElementById('errBanner');
    if(existing) existing.remove();
    wrap.insertAdjacentHTML('afterbegin',
      `<div class="card" id="errBanner" style="border-color:var(--red);margin-bottom:22px;">
         <h3 style="color:var(--red);">Could not load result.json</h3>
         <div style="color:var(--text-secondary);font-size:12.5px;line-height:1.7;">
           ${err.message}. Serve this folder over HTTP (browsers block fetch() on file:// pages):<br>
           <code>python -m http.server 8000</code> then open
           <code>http://localhost:8000/dashboard.html</code>. Run <code>python engine.py</code> first
           if result.json doesn't exist yet.
         </div>
       </div>`);
  }finally{
    btn.classList.remove('loading');
  }
}

document.getElementById('refreshBtn').addEventListener('click', loadResult);
loadResult();
