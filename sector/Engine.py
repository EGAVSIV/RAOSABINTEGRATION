import os
import json
import glob
from datetime import datetime

# =====================================================
# PATH CONFIGURATION (SECTOR FOLDER & DATA DIRECTORIES)
# =====================================================
# SECTOR_DIR points to the 'sector/' folder where Engine.py lives
SECTOR_DIR = os.path.dirname(os.path.abspath(__file__))
# ROOT_DIR points to the parent repository root folder
ROOT_DIR = os.path.abspath(os.path.join(SECTOR_DIR, ".."))

# Source data folders located in Root
DATA_SECTOR_FOLDER = os.path.join(ROOT_DIR, "sectorial_index_data")
DATA_STOCK_FOLDER = os.path.join(ROOT_DIR, "stockdata_D")

# Output files located inside the 'sector/' folder
OUTPUT_JSON = os.path.join(SECTOR_DIR, "scan_results.json")
OUTPUT_HTML = os.path.join(SECTOR_DIR, "index.html")

def load_json_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None

def extract_close_prices(data):
    if isinstance(data, list):
        sorted_data = sorted(data, key=lambda x: str(x.get('datetime', x.get('date', ''))))
        return [float(x.get('close', 0)) for x in sorted_data if 'close' in x]
    elif isinstance(data, dict):
        if 'close' in data:
            closes = data['close']
            if isinstance(closes, dict):
                keys = sorted(closes.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x))
                return [float(closes[k]) for k in keys]
    return []

def calculate_returns(prices, bars):
    if len(prices) <= bars:
        return None
    end = prices[-1]
    start = prices[-(bars + 1)]
    if start == 0:
        return 0.0
    return round(((end / start) - 1.0) * 100, 2)

def run_scanner():
    print(f"🚀 Running scanner engine inside: {SECTOR_DIR}")
    print(f"📁 Reading Sector Data from: {DATA_SECTOR_FOLDER}")
    print(f"📁 Reading Stock Data from: {DATA_STOCK_FOLDER}")

    nifty_path = os.path.join(DATA_SECTOR_FOLDER, "NIFTY.json")
    nifty_prices = []
    if os.path.exists(nifty_path):
        nifty_data = load_json_file(nifty_path)
        nifty_prices = extract_close_prices(nifty_data)

    nifty_1m = calculate_returns(nifty_prices, 21) or 0.0

    sector_results = []
    sector_files = glob.glob(os.path.join(DATA_SECTOR_FOLDER, "*.json"))
    for filepath in sector_files:
        filename = os.path.basename(filepath)
        if filename == "NIFTY.json":
            continue

        sector_name = filename.replace(".json", "")
        data = load_json_file(filepath)
        prices = extract_close_prices(data)

        r1m = calculate_returns(prices, 21)
        r3m = calculate_returns(prices, 63)
        r6m = calculate_returns(prices, 126)

        if r1m is not None:
            if r3m is not None:
                if r1m > 0 and r3m > 0: rotation = "Leading"
                elif r1m < 0 and r3m > 0: rotation = "Weakening"
                elif r1m < 0 and r3m < 0: rotation = "Lagging"
                else: rotation = "Improving"
            else:
                rotation = "N/A"

            rs_vs_nifty = round(r1m - nifty_1m, 2)
            momentum = round(r1m - (r3m or 0.0), 2)

            sector_results.append({
                "sector": sector_name,
                "return_1m": r1m,
                "return_3m": r3m if r3m is not None else 0.0,
                "return_6m": r6m if r6m is not None else 0.0,
                "rs_vs_nifty": rs_vs_nifty,
                "momentum": momentum,
                "rotation": rotation,
                "outperforming": r1m > nifty_1m
            })

    sector_results.sort(key=lambda x: x["return_1m"], reverse=True)
    for idx, sec in enumerate(sector_results):
        sec["rank"] = idx + 1

    stock_results = []
    stock_files = glob.glob(os.path.join(DATA_STOCK_FOLDER, "*.json"))
    for filepath in stock_files:
        stock_name = os.path.basename(filepath).replace(".json", "")
        data = load_json_file(filepath)
        prices = extract_close_prices(data)

        r1m = calculate_returns(prices, 21)
        r3m = calculate_returns(prices, 63)

        if r1m is not None:
            stock_results.append({
                "symbol": stock_name,
                "return_1m": r1m,
                "return_3m": r3m if r3m is not None else 0.0,
                "last_price": prices[-1] if prices else 0.0
            })

    scan_payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "nifty_1m_return": nifty_1m,
        "sectors": sector_results,
        "stocks": stock_results
    }

    # Save outputs directly inside sector/ folder
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(scan_payload, f, indent=2)

    print(f"✅ Created: {OUTPUT_JSON}")
    generate_html_dashboard(scan_payload)

def generate_html_dashboard(data_json):
    json_embedded = json.dumps(data_json)
    
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sector Rotation & Stock Scanner Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-dark: #0f172a;
            --panel-bg: #1e293b;
            --border-color: #334155;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --accent-green: #22c55e;
            --accent-red: #ef4444;
            --accent-blue: #3b82f6;
            --accent-orange: #f97316;
        }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            margin: 0;
            padding: 24px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 16px;
            margin-bottom: 24px;
        }}
        .grid-container {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }}
        .card {{
            background: var(--panel-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
        }}
        .chart-box {{ position: relative; height: 380px; width: 100%; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid var(--border-color); }}
        th {{ background-color: #0f172a; color: var(--text-muted); }}
        .tag {{ padding: 4px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: bold; }}
        .tag-leading {{ background: rgba(34, 197, 94, 0.2); color: var(--accent-green); }}
        .tag-improving {{ background: rgba(59, 130, 246, 0.2); color: var(--accent-blue); }}
        .tag-weakening {{ background: rgba(249, 115, 22, 0.2); color: var(--accent-orange); }}
        .tag-lagging {{ background: rgba(239, 68, 68, 0.2); color: var(--accent-red); }}
        .search-bar {{
            width: 100%; padding: 10px; border-radius: 6px;
            border: 1px solid var(--border-color); background: var(--bg-dark);
            color: #fff; margin-bottom: 10px; box-sizing: border-box;
        }}
        footer {{ margin-top: 40px; text-align: center; border-top: 1px solid var(--border-color); padding-top: 20px; color: var(--text-muted); }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>📊 Sector Rotation & Analytics Dashboard</h1>
            <div>Last Scan: <span id="time-stamp"></span> | NIFTY 1M: <span id="nifty-val"></span>%</div>
        </div>
    </div>
    <div class="grid-container">
        <div class="card" style="grid-column: span 2;">
            <h2>🧭 Sector RRG Map (vs NIFTY)</h2>
            <div class="chart-box"><canvas id="rrgChart"></canvas></div>
        </div>
        <div class="card">
            <h2>📈 Sector Relative Performance (1M Return %)</h2>
            <div class="chart-box"><canvas id="barChart"></canvas></div>
        </div>
    </div>
    <div class="grid-container">
        <div class="card">
            <h2>🔁 Sector Rotation Data</h2>
            <div style="overflow-x:auto;">
                <table id="sectorTable">
                    <thead>
                        <tr><th>Rank</th><th>Sector</th><th>1M %</th><th>3M %</th><th>Status</th></tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
        <div class="card">
            <h2>🤖 Stock Scanner Results</h2>
            <input type="text" id="searchInput" class="search-bar" onkeyup="filterStocks()" placeholder="Search stocks...">
            <div style="max-height: 400px; overflow-y:auto;">
                <table id="stockTable">
                    <thead>
                        <tr><th>Symbol</th><th>Last Price</th><th>1M Return %</th></tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
    </div>
    <footer><b>Designed by: Gaurav Singh Yadav</b> | Built for Quantitative Intelligence</footer>
    <script>
        const dashboardData = {json_embedded};
        document.getElementById('time-stamp').innerText = dashboardData.generated_at;
        document.getElementById('nifty-val').innerText = dashboardData.nifty_1m_return;

        const sectorTb = document.querySelector('#sectorTable tbody');
        dashboardData.sectors.forEach(s => {{
            sectorTb.innerHTML += `<tr>
                <td><b>#${{s.rank}}</b></td>
                <td>${{s.sector}}</td>
                <td style="color: ${{s.return_1m >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}}">${{s.return_1m}}%</td>
                <td style="color: ${{s.return_3m >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}}">${{s.return_3m}}%</td>
                <td><span class="tag tag-${{s.rotation.toLowerCase()}}">${{s.rotation}}</span></td>
            </tr>`;
        }});

        function renderStocks(list) {{
            const stockTb = document.querySelector('#stockTable tbody');
            stockTb.innerHTML = '';
            list.forEach(stk => {{
                stockTb.innerHTML += `<tr>
                    <td><b>${{stk.symbol}}</b></td>
                    <td>${{stk.last_price}}</td>
                    <td style="color: ${{stk.return_1m >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}}">${{stk.return_1m}}%</td>
                </tr>`;
            }});
        }}
        renderStocks(dashboardData.stocks);

        function filterStocks() {{
            const val = document.getElementById('searchInput').value.toLowerCase();
            renderStocks(dashboardData.stocks.filter(s => s.symbol.toLowerCase().includes(val)));
        }}

        new Chart(document.getElementById('barChart'), {{
            type: 'bar',
            data: {{
                labels: dashboardData.sectors.map(s => s.sector),
                datasets: [{{
                    data: dashboardData.sectors.map(s => s.return_1m),
                    backgroundColor: dashboardData.sectors.map(s => s.return_1m >= 0 ? '#22c55e' : '#ef4444')
                }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
        }});

        new Chart(document.getElementById('rrgChart'), {{
            type: 'scatter',
            data: {{
                datasets: [{{
                    data: dashboardData.sectors.map(s => ({{ x: s.rs_vs_nifty, y: s.momentum, name: s.sector }})),
                    backgroundColor: '#3b82f6', pointRadius: 8
                }}]
            }},
            options: {{
                responsive: true, maintainAspectRatio: false,
                plugins: {{ tooltip: {{ callbacks: {{ label: (ctx) => ctx.raw.name + ': (RS: ' + ctx.raw.x + ', Mom: ' + ctx.raw.y + ')' }} }} }},
                scales: {{
                    x: {{ title: {{ display: true, text: 'Relative Strength vs NIFTY (1M %)', color: '#94a3b8' }} }},
                    y: {{ title: {{ display: true, text: 'Momentum (1M - 3M)', color: '#94a3b8' }} }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
    with open(OUTPUT_HTML, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✅ Created: {OUTPUT_HTML}")

if __name__ == "__main__":
    run_scanner()
