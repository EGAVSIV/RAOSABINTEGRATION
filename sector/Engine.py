import os
import glob
import json
import math
import pandas as pd
import numpy as np
from datetime import datetime
from fpdf import FPDF
from fpdf.enums import XPos, YPos

# =====================================================
# PATH CONFIGURATION
# =====================================================
SECTOR_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(SECTOR_DIR, ".."))

DATA_SECTOR_FOLDER = os.path.join(ROOT_DIR, "sectorial_index_data")
DATA_STOCK_FOLDER = os.path.join(ROOT_DIR, "stockdata_D")
STATE_FILE = os.path.join(SECTOR_DIR, "sector_rotation_state.json")

OUTPUT_JSON = os.path.join(SECTOR_DIR, "scan_results.json")
OUTPUT_HTML = os.path.join(SECTOR_DIR, "index.html")
OUTPUT_PDF = os.path.join(SECTOR_DIR, "sector_rotation_weekly_report.pdf")

# Sector Stock Mappings from Streamlit dashboard
SECTOR_STOCKS = {
    "CNXIT": ["TCS", "INFY", "WIPRO", "HCLTECH", "LTIM", "TECHM", "COFORGE", "MPHASIS", "OFSS"],
    "CNXAUTO": ["TMPV", "MARUTI", "M&M", "EICHERMOT", "BOSCHLTD", "HEROMOTOCO", "ASHOKLEY", "UNOMINDA", "BHARATFORG", "TIINDIA", "SONACOMS", "EXIDEIND"],
    "CNXFINANCE": ["HDFCBANK", "ICICIBANK", "AXISBANK", "SBIN", "BAJFINANCE", "KOTAKBANK", "BAJAJFINSV", "SBILIFE", "JIOFIN", "SHRIRAMFIN", "HDFCLIFE", "MUTHOOTFIN", "CHOLAFIN", "PFC", "BSE", "ICICIGI", "ICICIPRULI", "RECLTD", "SBICARD", "LICHSGFIN"],
    "BANKNIFTY": ["HDFCBANK", "ICICIBANK", "AXISBANK", "PNB", "KOTAKBANK", "SBIN", "IDFCFIRSTB", "AUBANK", "INDUSINDBK", "CANBK", "BANKBARODA", "FEDERALBNK"],
    "CNXMETAL": ["HINDCOPPER", "HINDZINC", "VEDL", "ADANIENT", "HINDALCO", "TATASTEEL", "JINDALSTEL", "NMDC", "JSL", "SAIL", "APLAPOLLO"],
    "CNXPHARMA": ["SUNPHARMA", "GRANULES", "DIVISLAB", "CIPLA", "TORNTPHARM", "DRREDDY", "LUPIN", "ZYDUSLIFE", "AUROPHARMA", "ABBOTINDIA", "ALKEM", "MANKIND", "LAURUSLABS", "GLENMARK", "BIOCON", "IPCALAB"],
    "CNXFMCG": ["VBL", "GODREJCP", "COLPAL", "BRITANNIA", "DABUR", "HINDUNILVR", "ITC", "MARICO", "NESTLEIND", "PATANJALI", "UNITDSPR", "TATACONSUM"],
    "CNXENERGY": ["NTPC", "RELIANCE", "ONGC", "POWERGRID", "COALINDIA", "IOC", "ADANIGREEN", "BPCL", "GAIL", "TATAPOWER", "SIEMENS", "ABB", "CGPOWER", "BHEL", "JSWENERGY", "SUZLON", "INOXWIND", "PETRONET", "TORNTPOWER", "OIL", "NHPC", "HINDPETRO", "ADANIENSOL"],
    "CNXREALTY": ["DLF", "LODHA", "GODREJPROP", "OBEROIRLTY", "PHOENIXLTD", "PRESTIGE"],
    "NIFTY_HEALTHCARE": ["FORTIS", "MAXHEALTH", "APOLLOHOSP", "SUNPHARMA", "ZYDUSLIFE", "LAURUSLABS", "DRREDDY", "DIVISLAB", "CIPLA", "SYNGENE", "ALKEM", "TORNTPHARM", "AUROPHARMA", "GLENMARK", "MANKIND", "BIOCON", "LUPIN"],
    "NIFTY_IND_DEFENCE": ["SOLARINDS", "BDL", "BEL", "HAL", "MAZDOCK"],
    "NIFTY_CAPITAL_MKT": ["NUVAMA", "MCX", "ANGELONE", "BSE", "CAMS", "CDSL", "HDFCAMC", "360ONE", "KFINTECH", "IEX"],
    "NIFTY_TOP_10_EW": ["RELIANCE", "KOTAKBANK", "BHARTIARTL", "HDFCBANK", "INFY", "LT", "ITC", "TCS", "ICICIBANK", "AXISBANK"],
    "NIFTY_NEW_CONSUMP": ["360ONE", "AMBER", "ANGELONE", "BAJAJ_AUTO", "BHARTIARTL", "BLUESTARCO", "CROMPTON", "DIXON", "DLF", "DMART", "EICHERMOT", "ETERNAL", "GODREJPROP", "HAVELLS", "HDFCAMC", "HEROMOTOCO", "IDEA", "INDHOTEL", "INDIAMART", "INDIGO", "IRCTC", "JUBLFOOD", "KALYANKJIL", "LODHA", "M&M", "MARUTI", "NAUKRI", "NUVAMA", "NYKAA", "OBEROIRLTY", "PAGEIND", "PAYTM"],
    "CNXPSE": ["BEL", "BHEL", "BPCL", "COALINDIA", "CONCOR", "GAIL", "HAL", "HINDPETRO", "IOC", "IRCTC", "IRFC", "NHPC", "NMDC", "NTPC", "ONGC", "PFC", "POWERGRID", "RECLTD", "RVNL"],
    "NIFTY_CONSR_DURBL": ["TITAN", "KALYANKJIL", "CROMPTON", "AMBER", "BLUESTARCO", "VOLTAS", "HAVELLS", "PGEL", "DIXON"],
    "CNXINFRA": ["ULTRACEMCO", "TATAPOWER", "SIEMENS", "SHREECEM", "RELIANCE", "POWERGRID", "ONGC", "NTPC", "MOTHERSON", "MAXHEALTH", "LT", "IOC", "INDUSTOWER", "INDIGO", "INDHOTEL", "HINDPETRO", "GRASIM", "GODREJPROP", "GAIL", "DLF", "CUMMINSIND", "CGPOWER", "BPCL", "BHARTIARTL", "BHARATFORG", "ASHOKLEY", "APOLLOHOSP", "AMBUJACEM", "ADANIPORTS", "ADANIGREEN"]
}

def load_series(folder, name):
    """Loads time series from JSON or Parquet files."""
    json_p = os.path.join(folder, f"{name}.json")
    pq_p = os.path.join(folder, f"{name}.parquet")

    if os.path.exists(pq_p):
        try:
            df = pd.read_parquet(pq_p)
            if isinstance(df.index, pd.MultiIndex):
                df = df.reset_index()
            elif "datetime" in df.index.names:
                df = df.reset_index()
            date_col = "datetime" if "datetime" in df.columns else "date"
            df[date_col] = pd.to_datetime(df[date_col])
            df = df.sort_values(date_col)
            return df["close"].values.astype(float)
        except Exception:
            pass

    if os.path.exists(json_p):
        try:
            with open(json_p, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                sorted_d = sorted(data, key=lambda x: str(x.get('datetime', x.get('date', ''))))
                return [float(x.get('close', 0)) for x in sorted_d if 'close' in x]
            elif isinstance(data, dict) and 'close' in data:
                closes = data['close']
                if isinstance(closes, dict):
                    keys = sorted(closes.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x))
                    return [float(closes[k]) for k in keys]
        except Exception:
            pass

    return None

def calc_return(prices, bars):
    if prices is None or len(prices) <= bars:
        return None
    end = prices[-1]
    start = prices[-(bars + 1)]
    if start == 0:
        return 0.0
    return round(((end / start) - 1.0) * 100, 2)

def classify_rotation(r1m, r3m):
    if r1m > 0 and r3m > 0: return "Leading"
    if r1m < 0 and r3m > 0: return "Weakening"
    if r1m < 0 and r3m < 0: return "Lagging"
    return "Improving"

def run_scanner():
    print(f"🚀 Processing Sector & Stock Analytics Engine...")

    nifty_prices = load_series(DATA_SECTOR_FOLDER, "NIFTY")
    nifty_1m = calc_return(nifty_prices, 21) or 0.0

    # Sector calculations
    sector_results = []
    files = glob.glob(os.path.join(DATA_SECTOR_FOLDER, "*.*"))
    sector_names = sorted(list(set([os.path.splitext(os.path.basename(f))[0] for f in files])))

    for sec in sector_names:
        if sec == "NIFTY":
            continue
        prices = load_series(DATA_SECTOR_FOLDER, sec)
        if prices is None:
            continue

        r1m = calc_return(prices, 21)
        r3m = calc_return(prices, 63)
        r6m = calc_return(prices, 126)

        if r1m is not None and r3m is not None:
            rotation = classify_rotation(r1m, r3m)
            rs_vs_nifty = round(r1m - nifty_1m, 2)
            momentum = round(r1m - r3m, 2)

            sector_results.append({
                "sector": sec,
                "return_1m": r1m,
                "return_3m": r3m,
                "return_6m": r6m if r6m is not None else 0.0,
                "nifty_1m": nifty_1m,
                "status": "Outperforming" if r1m > nifty_1m else "Underperforming",
                "rs_vs_nifty": rs_vs_nifty,
                "momentum": momentum,
                "rotation": rotation
            })

    # Sector Ranking
    sector_results.sort(key=lambda x: x["return_1m"], reverse=True)
    for idx, s in enumerate(sector_results):
        s["rs_rank"] = idx + 1

    # Sector Weight-Adjusted Portfolio
    leading_improving = [s for s in sector_results if s["rotation"] in ["Leading", "Improving"]]
    max_rank = len(sector_results) + 1
    total_raw = sum([max_rank - s["rs_rank"] for s in leading_improving]) or 1

    portfolio = []
    for s in leading_improving:
        raw_w = max_rank - s["rs_rank"]
        weight = round((raw_w / total_raw) * 100, 2)
        portfolio.append({
            "sector": s["sector"],
            "rotation": s["rotation"],
            "rs_rank": s["rs_rank"],
            "weight_pct": weight
        })

    # Sector Rotation Alerts
    prev_state = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                prev_state = json.load(f)
        except Exception:
            pass

    alerts = []
    current_state = {}
    for s in sector_results:
        sec = s["sector"]
        rot = s["rotation"]
        current_state[sec] = rot
        if sec in prev_state and prev_state[sec] != rot:
            alerts.append(f"{sec}: {prev_state[sec]} ➔ {rot}")

    with open(STATE_FILE, 'w') as f:
        json.dump(current_state, f, indent=2)

    # Stock-Level RRG & Sector-Based Top Stock Scanner
    stock_rrg_by_sector = {}
    stock_scanner = []

    for sec, stock_list in SECTOR_STOCKS.items():
        sec_prices = load_series(DATA_SECTOR_FOLDER, sec)
        sec_1m = calc_return(sec_prices, 21) or 0.0
        
        stock_rrg_by_sector[sec] = []

        for stock in stock_list:
            sp = load_series(DATA_STOCK_FOLDER, stock)
            if sp is None:
                continue

            sr1 = calc_return(sp, 21)
            sr3 = calc_return(sp, 63)
            last_p = round(sp[-1], 2) if len(sp) > 0 else 0.0

            if sr1 is not None and sr3 is not None:
                rs_vs_sec = round(sr1 - sec_1m, 2)
                stock_mom = round(sr1 - sr3, 2)

                stock_rrg_by_sector[sec].append({
                    "stock": stock,
                    "return_1m": sr1,
                    "return_3m": sr3,
                    "last_price": last_p,
                    "rs_vs_sector": rs_vs_sec,
                    "momentum": stock_mom
                })

                if sec in [p["sector"] for p in portfolio] and sr1 > sec_1m:
                    stock_scanner.append({
                        "sector": sec,
                        "stock": stock,
                        "stock_1m": sr1,
                        "sector_1m": sec_1m,
                        "signal": "Sector Leader"
                    })

    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nifty_1m_return": nifty_1m,
        "sectors": sector_results,
        "top5_sectors": sector_results[:5],
        "portfolio": portfolio,
        "alerts": alerts,
        "stock_rrg": stock_rrg_by_sector,
        "stock_scanner": stock_scanner
    }

    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)

    generate_pdf_report(sector_results)
    generate_html_dashboard(payload)

def generate_pdf_report(sectors):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.cell(0, 10, "Weekly Sector Rotation Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(5)

    pdf.set_font("Helvetica", style="B", size=10)
    pdf.cell(20, 8, "Rank", border=1)
    pdf.cell(50, 8, "Sector", border=1)
    pdf.cell(30, 8, "1M Return %", border=1)
    pdf.cell(30, 8, "3M Return %", border=1)
    pdf.cell(45, 8, "Rotation Status", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.set_font("Helvetica", size=10)
    for s in sectors:
        pdf.cell(20, 8, f"#{s['rs_rank']}", border=1)
        pdf.cell(50, 8, str(s['sector']), border=1)
        pdf.cell(30, 8, f"{s['return_1m']}%", border=1)
        pdf.cell(30, 8, f"{s['return_3m']}%", border=1)
        pdf.cell(45, 8, str(s['rotation']), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.output(OUTPUT_PDF)
    print(f"✅ Generated PDF: {OUTPUT_PDF}")

def generate_html_dashboard(data):
    embedded_json = json.dumps(data)

    html_code = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sector Rotation & Analytics Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">
    <style>
        :root {{
            --bg-main: #0b0f19;
            --card-bg: #151c2c;
            --border-color: #232d42;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --accent-green: #22c55e;
            --accent-red: #ef4444;
            --accent-blue: #3b82f6;
            --accent-orange: #f97316;
        }}
        body {{
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-main);
            color: var(--text-main);
            margin: 0; padding: 24px;
        }}
        .header {{
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid var(--border-color); padding-bottom: 16px; margin-bottom: 24px;
        }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 20px; margin-bottom: 24px; }}
        .card {{ background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; }}
        .full-width {{ grid-column: 1 / -1; }}
        .chart-container {{ position: relative; height: 380px; width: 100%; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.9rem; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border-color); }}
        th {{ background: #0f172a; color: var(--text-muted); font-weight: 600; }}
        .badge {{ padding: 4px 8px; border-radius: 6px; font-size: 0.75rem; font-weight: bold; text-transform: uppercase; }}
        .badge-leading {{ background: rgba(34, 197, 94, 0.2); color: var(--accent-green); }}
        .badge-improving {{ background: rgba(59, 130, 246, 0.2); color: var(--accent-blue); }}
        .badge-weakening {{ background: rgba(249, 115, 22, 0.2); color: var(--accent-orange); }}
        .badge-lagging {{ background: rgba(239, 68, 68, 0.2); color: var(--accent-red); }}
        .alert-box {{ background: rgba(249, 115, 22, 0.1); border-left: 4px solid var(--accent-orange); padding: 12px; border-radius: 4px; margin-bottom: 8px; }}
        .select-input, .search-bar {{
            width: 100%; padding: 10px; border-radius: 6px; border: 1px solid var(--border-color);
            background: #0f172a; color: white; margin-bottom: 12px; box-sizing: border-box;
        }}
        .btn-download {{
            display: inline-block; background: var(--accent-blue); color: white; padding: 10px 16px;
            border-radius: 6px; text-decoration: none; font-weight: bold; margin-top: 10px;
        }}
        footer {{ border-top: 1px solid var(--border-color); padding-top: 24px; margin-top: 40px; color: var(--text-muted); line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>📊 Sector Rotation & Analytics Dashboard</h1>
            <p style="color: var(--text-muted); margin: 4px 0 0 0;">
                Sector Performance | RRG | Rotation | Portfolio | Scanner
            </p>
        </div>
        <div>
            🕒 Last Refresh (IST): <b><span id="gen-time"></span></b> | NIFTY 1M: <b><span id="nifty-val"></span>%</b>
        </div>
    </div>

    <div class="grid">
        <!-- 🧭 RRG Sector Map -->
        <div class="card">
            <h2>🧭 RRG-Style Sector Map (vs NIFTY)</h2>
            <div class="chart-container"><canvas id="sectorRRGCanvas"></canvas></div>
        </div>

        <!-- 📈 Relative Performance Chart -->
        <div class="card">
            <h2>📈 Relative Performance Chart</h2>
            <div class="chart-container"><canvas id="perfChartCanvas"></canvas></div>
        </div>
    </div>

    <div class="grid">
        <!-- 📋 Performance & Rotation Table -->
        <div class="card">
            <h2>📋 Performance & Rotation Table</h2>
            <div style="max-height: 400px; overflow-y: auto;">
                <table>
                    <thead>
                        <tr><th>Rank</th><th>Sector</th><th>1M %</th><th>3M %</th><th>6M %</th><th>Status</th></tr>
                    </thead>
                    <tbody id="sectorTableBody"></tbody>
                </table>
            </div>
        </div>

        <!-- 🏆 Top 5 Sectors & Alerts -->
        <div class="card">
            <h2>🏆 Top 5 Strongest Sectors</h2>
            <table>
                <thead>
                    <tr><th>Rank</th><th>Sector</th><th>1M %</th><th>Rotation</th></tr>
                </thead>
                <tbody id="top5TableBody"></tbody>
            </table>

            <h2 style="margin-top: 24px;">🚨 Sector Rotation Change Alerts</h2>
            <div id="alertsContainer"></div>
        </div>
    </div>

    <div class="grid">
        <!-- 📈 Stock-Level RRG Inside Sector -->
        <div class="card">
            <h2>📈 Stock-Level RRG Inside Sector</h2>
            <select id="sectorSelect" class="select-input" onchange="updateStockRRG()"></select>
            <div class="chart-container"><canvas id="stockRRGCanvas"></canvas></div>
        </div>

        <!-- 🧮 Sector Weight-Adjusted Portfolio -->
        <div class="card">
            <h2>🧮 Sector Weight-Adjusted Portfolio</h2>
            <table>
                <thead>
                    <tr><th>Sector</th><th>Rotation</th><th>RS Rank</th><th>Weight %</th></tr>
                </thead>
                <tbody id="portfolioTableBody"></tbody>
            </table>
        </div>
    </div>

    <div class="grid">
        <!-- 🤖 Sector-Based Top Stock Scanner -->
        <div class="card">
            <h2>🤖 Sector-Based Top Stock Scanner</h2>
            <input type="text" id="stockSearch" class="search-bar" placeholder="Search scanner stocks..." onkeyup="filterScanner()">
            <div style="max-height: 300px; overflow-y: auto;">
                <table>
                    <thead>
                        <tr><th>Sector</th><th>Stock</th><th>Stock 1M %</th><th>Sector 1M %</th><th>Signal</th></tr>
                    </thead>
                    <tbody id="scannerTableBody"></tbody>
                </table>
            </div>
        </div>

        <!-- 📄 PDF Export -->
        <div class="card">
            <h2>📄 Weekly Sector Rotation Report</h2>
            <p>Download the full weekly performance analysis report in PDF format.</p>
            <a href="sector_rotation_weekly_report.pdf" download class="btn-download">📥 Download Weekly PDF Report</a>
        </div>
    </div>

    <footer>
        <div style="line-height: 1.6;">
            <b>Designed by:-<br>Gaurav Singh Yadav</b><br><br>
            🩷💛🩵💙🩶💜🤍🤎💖 Built With Love 🫶<br>
            Energy | Commodity | Quant Intelligence 📶<br><br>
            📱 +91-8003994518 〽️<br>
            💬 <a href="https://wa.me/918003994518" target="_blank" style="color:#25D366; text-decoration:none;">
            <i class="fa fa-whatsapp"></i> WhatsApp</a><br>
            📧 <a href="mailto:yadav.gauravsingh@gmail.com" style="color: var(--accent-blue);">yadav.gauravsingh@gmail.com</a> ™️
        </div>
    </footer>

    <script>
        const DATA = {embedded_json};
        let stockRRGChartInstance = null;

        document.getElementById('gen-time').innerText = DATA.generated_at;
        document.getElementById('nifty-val').innerText = DATA.nifty_1m_return;

        // Populate Sector Table
        const sectorTb = document.getElementById('sectorTableBody');
        DATA.sectors.forEach(s => {{
            sectorTb.innerHTML += `<tr>
                <td><b>#${{s.rs_rank}}</b></td>
                <td>${{s.sector}}</td>
                <td style="color:${{s.return_1m >= 0 ? 'var(--accent-green)':'var(--accent-red)'}}">${{s.return_1m}}%</td>
                <td style="color:${{s.return_3m >= 0 ? 'var(--accent-green)':'var(--accent-red)'}}">${{s.return_3m}}%</td>
                <td style="color:${{s.return_6m >= 0 ? 'var(--accent-green)':'var(--accent-red)'}}">${{s.return_6m}}%</td>
                <td><span class="badge badge-${{s.rotation.toLowerCase()}}">${{s.rotation}}</span></td>
            </tr>`;
        }});

        // Populate Top 5 Table
        const top5Tb = document.getElementById('top5TableBody');
        DATA.top5_sectors.forEach(s => {{
            top5Tb.innerHTML += `<tr>
                <td><b>#${{s.rs_rank}}</b></td>
                <td>${{s.sector}}</td>
                <td style="color:var(--accent-green)">${{s.return_1m}}%</td>
                <td><span class="badge badge-${{s.rotation.toLowerCase()}}">${{s.rotation}}</span></td>
            </tr>`;
        }});

        // Alerts
        const alertsDiv = document.getElementById('alertsContainer');
        if (DATA.alerts.length > 0) {{
            DATA.alerts.forEach(a => {{
                alertsDiv.innerHTML += `<div class="alert-box">⚠️ ${{a}}</div>`;
            }});
        }} else {{
            alertsDiv.innerHTML = `<div style="color: var(--accent-green);">No sector rotation changes.</div>`;
        }}

        // Portfolio Table
        const portTb = document.getElementById('portfolioTableBody');
        DATA.portfolio.forEach(p => {{
            portTb.innerHTML += `<tr>
                <td><b>${{p.sector}}</b></td>
                <td><span class="badge badge-${{p.rotation.toLowerCase()}}">${{p.rotation}}</span></td>
                <td>#${{p.rs_rank}}</td>
                <td><b>${{p.weight_pct}}%</b></td>
            </tr>`;
        }});

        // Scanner Table
        function renderScanner(list) {{
            const scanTb = document.getElementById('scannerTableBody');
            scanTb.innerHTML = '';
            list.forEach(stk => {{
                scanTb.innerHTML += `<tr>
                    <td>${{stk.sector}}</td>
                    <td><b>${{stk.stock}}</b></td>
                    <td style="color:var(--accent-green)">${{stk.stock_1m}}%</td>
                    <td>${{stk.sector_1m}}%</td>
                    <td><span class="badge badge-leading">${{stk.signal}}</span></td>
                </tr>`;
            }});
        }}
        renderScanner(DATA.stock_scanner);

        function filterScanner() {{
            const query = document.getElementById('stockSearch').value.toLowerCase();
            renderScanner(DATA.stock_scanner.filter(s => s.stock.toLowerCase().includes(query) || s.sector.toLowerCase().includes(query)));
        }}

        // Performance Chart
        new Chart(document.getElementById('perfChartCanvas'), {{
            type: 'bar',
            data: {{
                labels: DATA.sectors.map(s => s.sector),
                datasets: [{{
                    data: DATA.sectors.map(s => s.return_1m),
                    backgroundColor: DATA.sectors.map(s => s.return_1m >= 0 ? '#22c55e' : '#ef4444')
                }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
        }});

        // Sector RRG Quadrant Chart
        new Chart(document.getElementById('sectorRRGCanvas'), {{
            type: 'scatter',
            data: {{
                datasets: [{{
                    data: DATA.sectors.map(s => ({{ x: s.rs_vs_nifty, y: s.momentum, name: s.sector }})),
                    backgroundColor: '#3b82f6', pointRadius: 7
                }}]
            }},
            options: {{
                responsive: true, maintainAspectRatio: false,
                plugins: {{
                    tooltip: {{ callbacks: {{ label: (ctx) => ctx.raw.name + ' (RS: ' + ctx.raw.x + ', Mom: ' + ctx.raw.y + ')' }} }}
                }},
                scales: {{
                    x: {{ title: {{ display: true, text: 'Relative Strength vs NIFTY (1M %)', color: '#94a3b8' }} }},
                    y: {{ title: {{ display: true, text: 'Momentum (1M - 3M)', color: '#94a3b8' }} }}
                }}
            }}
        }});

        // Stock Level RRG Selector setup
        const select = document.getElementById('sectorSelect');
        Object.keys(DATA.stock_rrg).forEach(sec => {{
            select.innerHTML += `<option value="${{sec}}">${{sec}}</option>`;
        }});

        function updateStockRRG() {{
            const selectedSector = select.value;
            const stockData = DATA.stock_rrg[selectedSector] || [];

            if (stockRRGChartInstance) stockRRGChartInstance.destroy();

            stockRRGChartInstance = new Chart(document.getElementById('stockRRGCanvas'), {{
                type: 'scatter',
                data: {{
                    datasets: [{{
                        data: stockData.map(s => ({{ x: s.rs_vs_sector, y: s.momentum, name: s.stock }})),
                        backgroundColor: '#22c55e', pointRadius: 6
                    }}]
                }},
                options: {{
                    responsive: true, maintainAspectRatio: false,
                    plugins: {{
                        tooltip: {{ callbacks: {{ label: (ctx) => ctx.raw.name + ' (RS: ' + ctx.raw.x + ', Mom: ' + ctx.raw.y + ')' }} }}
                    }},
                    scales: {{
                        x: {{ title: {{ display: true, text: 'RS vs Sector (1M %)', color: '#94a3b8' }} }},
                        y: {{ title: {{ display: true, text: 'Momentum (1M - 3M)', color: '#94a3b8' }} }}
                    }}
                }}
            }});
        }}
        updateStockRRG();
    </script>
</body>
</html>
"""
    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html_code)
    print(f"✅ Generated HTML: {OUTPUT_HTML}")

if __name__ == "__main__":
    run_scanner()
