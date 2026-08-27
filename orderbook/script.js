let globalData = { announcements: [], rankings: [] };
let impactChartInstance = null;
let sectorChartInstance = null;

function updateClock(){
    const now = new Date();
    const opts = { weekday:'short', year:'numeric', month:'short', day:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12:true, timeZone:'Asia/Kolkata' };
    document.getElementById('liveDate').textContent = now.toLocaleString('en-IN', opts) + ' IST';
}
updateClock();
setInterval(updateClock, 1000);

async function loadData() {
    try {
        const response = await fetch('nse_orders_data.json');
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        globalData = await response.json();

        populateFilters();
        renderMetrics(globalData.rankings || []);
        renderRankings(globalData.rankings || []);
        renderAnnouncements(globalData.announcements || []);
        renderTicker(globalData.rankings || []);
        renderCharts(globalData.rankings || []);
    } catch (error) {
        console.error("Error loading JSON file data:", error);
        document.getElementById('tickerTrack').innerHTML = '<span><b>⚠ Could not load nse_orders_data.json — place it alongside this file.</b></span>';
    }
}

function populateFilters() {
    const stockSelect = document.getElementById('stockFilter');
    const symbols = [...new Set((globalData.announcements || []).map(item => item.symbol))].sort();
    symbols.forEach(sym => {
        if(sym) {
            const option = document.createElement('option');
            option.value = sym;
            option.textContent = sym;
            stockSelect.appendChild(option);
        }
    });

    const descSelect = document.getElementById('descFilter');
    if (descSelect) {
        const descriptions = [...new Set((globalData.announcements || []).map(item => item.desc))].filter(Boolean).sort();
        descriptions.forEach(desc => {
            const option = document.createElement('option');
            option.value = desc;
            option.textContent = desc;
            descSelect.appendChild(option);
        });
    }
}

function applyFilters() {
    const stock = document.getElementById('stockFilter').value;
    const descElement = document.getElementById('descFilter');
    const desc = descElement ? descElement.value : 'All';
    const search = document.getElementById('searchFilter').value.toLowerCase();

    const filteredAnnouncements = (globalData.announcements || []).filter(a => {
        const matchesStock = stock === 'All' || a.symbol === stock;
        const matchesDesc = desc === 'All' || a.desc === desc;
        const matchesSearch = (a.symbol && a.symbol.toLowerCase().includes(search)) ||
                              (a.sm_name && a.sm_name.toLowerCase().includes(search));
        return matchesStock && matchesDesc && matchesSearch;
    });

    const validSymbols = new Set(filteredAnnouncements.map(a => a.symbol));

    const filteredRankings = (globalData.rankings || []).filter(r => {
        const matchesStock = stock === 'All' || r.symbol === stock;
        const matchesDesc = desc === 'All' || r.desc === desc || validSymbols.has(r.symbol);
        const matchesSearch = (r.symbol && r.symbol.toLowerCase().includes(search)) ||
                              (r.company && r.company.toLowerCase().includes(search));
        return matchesStock && matchesDesc && matchesSearch;
    });

    renderRankings(filteredRankings);
    renderAnnouncements(filteredAnnouncements);
    renderMetrics(filteredRankings);
    renderCharts(filteredRankings);
}

function impactTier(score){
    if (score > 50) return { cls: 'high', label: 'High' };
    if (score > 20) return { cls: 'mid', label: 'Mid' };
    return { cls: 'low', label: 'Low' };
}

function fmtNum(n){
    if (n === undefined || n === null || isNaN(n)) return '—';
    return Number(n).toLocaleString('en-IN');
}

function renderMetrics(rankings) {
    document.getElementById('metric-total').innerText = rankings.length;
    const maxImpact = rankings.length ? Math.max(...rankings.map(r => r.impact_score || 0)) : 0;
    document.getElementById('metric-max-impact').innerText = fmtNum(maxImpact);
    const totalVal = rankings.reduce((acc, curr) => acc + (curr.order_val_cr || 0), 0);
    document.getElementById('metric-total-val').innerText = totalVal.toLocaleString('en-IN');
}

function renderTicker(rankings) {
    const track = document.getElementById('tickerTrack');
    if (!rankings.length) {
        track.innerHTML = '<span><b>No ranked orders available yet.</b></span>';
        return;
    }
    const top = [...rankings].sort((a,b) => (b.impact_score||0) - (a.impact_score||0)).slice(0, 15);
    const buildItems = () => top.map(r => {
        const tier = impactTier(r.impact_score || 0);
        const cls = tier.cls === 'high' ? 't-high' : (tier.cls === 'mid' ? 't-mid' : 't-up');
        return `<span><b>${r.symbol || '—'}</b> ₹${fmtNum(r.order_val_cr)} Cr &nbsp;<span class="${cls}">● Impact ${fmtNum(r.impact_score)}</span></span>`;
    }).join('');
    track.innerHTML = buildItems() + buildItems();
}

function renderRankings(rankings) {
    const tbody = document.getElementById('rankingsTable');
    if (!rankings.length) {
        tbody.innerHTML = `<tr class="empty-row"><td colspan="9"><i class="fa-solid fa-inbox"></i> No matching orders found</td></tr>`;
        return;
    }
    tbody.innerHTML = rankings.map((r, i) => {
        const tier = impactTier(r.impact_score || 0);
        const dotColor = tier.cls === 'high' ? 'var(--crimson)' : (tier.cls === 'mid' ? 'var(--gold)' : 'var(--emerald)');
        const pct = Math.max(0, Math.min(100, r.order_pct_mcap || 0));
        return `
            <tr style="animation-delay:${Math.min(i * 0.03, 0.6)}s">
                <td>
                  <div class="sym-cell">
                    <span class="sym-dot" style="background:${dotColor}"></span>
                    <span class="sym-code">${r.symbol || '—'}</span>
                  </div>
                </td>
                <td>${r.company || '—'}</td>
                <td class="val-rupee">₹${fmtNum(r.order_val_cr)}</td>
                <td class="mono">₹${fmtNum(r.market_cap_cr)}</td>
                <td>
                  <div class="pct-bar-wrap">
                    <div class="pct-bar-track"><div class="pct-bar-fill" style="width:${pct}%"></div></div>
                    <span class="pct-label">${r.order_pct_mcap ?? '—'}%</span>
                  </div>
                </td>
                <td><span class="badge badge-${tier.cls}">${tier.label} · ${fmtNum(r.impact_score)}</span></td>
                <td class="mono">${r.completion_time || '—'}</td>
                <td><span class="sector-pill">${r.sector || '—'}</span></td>
                <td>
                  <div class="link-group">
                    <a href="${r.screener_url || '#'}" target="_blank"><i class="fa-solid fa-chart-simple"></i>Screener</a>
                    <a href="${r.pdf_url || '#'}" target="_blank"><i class="fa-solid fa-file-pdf"></i>PDF</a>
                  </div>
                </td>
            </tr>
        `;
    }).join('');
}

function renderAnnouncements(announcements) {
    const tbody = document.getElementById('announcementsTable');
    if (!announcements.length) {
        tbody.innerHTML = `<tr class="empty-row"><td colspan="5"><i class="fa-solid fa-inbox"></i> No matching announcements found</td></tr>`;
        return;
    }
    tbody.innerHTML = announcements.map((a, i) => `
        <tr style="animation-delay:${Math.min(i * 0.03, 0.6)}s">
            <td><span class="sym-code">${a.symbol || '—'}</span></td>
            <td>${a.sm_name || '—'}</td>
            <td class="wrap">${a.desc || '—'}</td>
            <td class="mono">${a.Date || '—'}</td>
            <td>
              <div class="link-group">
                <a href="${a.screener_url || '#'}" target="_blank"><i class="fa-solid fa-chart-simple"></i>Screener</a>
                <a href="${a.attchmntFile || '#'}" target="_blank"><i class="fa-solid fa-file-pdf"></i>PDF</a>
              </div>
            </td>
        </tr>
    `).join('');
}

function renderCharts(rankings) {
    if (typeof Chart === 'undefined') return;

    // ---- Impact chart (top 10 horizontal bars) ----
    const top10 = [...rankings].sort((a,b) => (b.impact_score||0) - (a.impact_score||0)).slice(0, 10);
    const impactCtx = document.getElementById('impactChart');
    const impactColors = top10.map(r => {
        const t = impactTier(r.impact_score || 0).cls;
        return t === 'high' ? '#fb4570' : (t === 'mid' ? '#f0b90b' : '#22c55e');
    });

    if (impactChartInstance) impactChartInstance.destroy();
    impactChartInstance = new Chart(impactCtx, {
        type: 'bar',
        data: {
            labels: top10.map(r => r.symbol || '—'),
            datasets: [{
                label: 'Impact Score',
                data: top10.map(r => r.impact_score || 0),
                backgroundColor: impactColors,
                borderRadius: 6,
                barThickness: 16
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 700, easing: 'easeOutQuart' },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#0c1120',
                    borderColor: 'rgba(240,185,11,0.35)',
                    borderWidth: 1,
                    titleFont: { family: 'JetBrains Mono' },
                    bodyFont: { family: 'JetBrains Mono' }
                }
            },
            scales: {
                x: { grid: { color: 'rgba(148,163,184,0.08)' }, ticks: { color: '#8592ac', font: { family: 'JetBrains Mono', size: 11 } } },
                y: { grid: { display: false }, ticks: { color: '#e9eefb', font: { family: 'JetBrains Mono', size: 11, weight: '600' } } }
            }
        }
    });

    // ---- Sector chart (doughnut of order value by sector) ----
    const sectorTotals = {};
    rankings.forEach(r => {
        const sector = r.sector || 'Unclassified';
        sectorTotals[sector] = (sectorTotals[sector] || 0) + (r.order_val_cr || 0);
    });
    const sectorLabels = Object.keys(sectorTotals);
    const sectorValues = Object.values(sectorTotals);
    const palette = ['#f0b90b', '#38d3f8', '#fb4570', '#22c55e', '#a78bfa', '#fb923c', '#f472b6', '#34d399', '#60a5fa', '#facc15'];

    const sectorCtx = document.getElementById('sectorChart');
    if (sectorChartInstance) sectorChartInstance.destroy();
    sectorChartInstance = new Chart(sectorCtx, {
        type: 'doughnut',
        data: {
            labels: sectorLabels,
            datasets: [{
                data: sectorValues,
                backgroundColor: sectorLabels.map((_, i) => palette[i % palette.length]),
                borderColor: '#0c1120',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 700, easing: 'easeOutQuart' },
            cutout: '62%',
            plugins: {
                legend: {
                    position: 'right',
                    labels: { color: '#8592ac', font: { family: 'JetBrains Mono', size: 10.5 }, boxWidth: 10, padding: 10 }
                },
                tooltip: {
                    backgroundColor: '#0c1120',
                    borderColor: 'rgba(56,211,248,0.35)',
                    borderWidth: 1,
                    titleFont: { family: 'JetBrains Mono' },
                    bodyFont: { family: 'JetBrains Mono' },
                    callbacks: {
                        label: (ctx) => ` ₹${fmtNum(ctx.parsed)} Cr`
                    }
                }
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', loadData);
