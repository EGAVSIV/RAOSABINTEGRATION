import os
import sys
import logging
import smtplib
import mimetypes
import urllib.request
import urllib.parse
from datetime import datetime
from email.message import EmailMessage

import numpy as np
import pandas as pd
import talib

# Set matplotlib backend to non-interactive before importing pyplot
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ==============================================================================
# 1. LOGGING SETUP
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("NSE_Scanner")

# ==============================================================================
# 2. GLOBAL CONFIGURATION
# ==============================================================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "nse.scanner.app@gmail.com"
SENDER_PASSWORD = "wmkdozoyfprduqgx"
RECIPIENTS = ["yadav.gauravsingh@gmail.com"]
BCC_RECIPIENTS = ["dipti.gorwadia@gmail.com", "yadav.gauravsingh34@gmail.com", "akshay.tiwari@gmail.com"]

TELEGRAM_BOT_TOKEN = "8344354642:AAG_S7mavtiLP_yXPh4YM4u31QD5BBWJmuM"
TELEGRAM_CHAT_IDS = ["5332984891", "-1002622207173"]

# New BASE_PATH (points to the parent repository root folder):
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
BASE_PATH = os.path.dirname(SCRIPT_DIR) # Moves 1 level up to the root folder
#BASE_PATH = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
OUTPUT_DIR = os.path.join(BASE_PATH, "Output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# UPDATED FOLDER NAMES ACCORDING TO IMAGE
TIMEFRAME_FOLDERS = {
    "15 Min": ("stockdata_15", "15 Min Scan"),
    "Hourly": ("stockdata_1H", "Hourly Scan"),
    "Daily": ("stockdata_D", "Daily Scan"),
    "Weekly": ("stockdata_W", "Weekly Scan"),
    "Monthly": ("stockdata_M", "Monthly Scan"),
}

SAFE_COLS = [
    "Symbol", "Signal", "Trend", "State", "Setup", 
    "Divergence", "RSI", "Zone", "Confluence", "Bias", 
    "Probability", "TV_Link"
]

def make_tradingview_link(sym: str) -> str:
    return f"https://in.tradingview.com/chart/LqUZraZ9/?symbol=NSE%3A{sym}"

# ==============================================================================
# 3. TECHNICAL SCANNING DEFINITIONS (Core Mathematical Logic)
# ==============================================================================
def run_rsi_market_pulse(df):
    if len(df) < 14:
        return None, None
    rsi = talib.RSI(df["close"], 14).iloc[-1]
    if rsi > 60:
        zone = "RSI > 60"
    elif rsi < 40:
        zone = "RSI < 40"
    else:
        zone = "RSI 40–60"
    return round(rsi, 2), zone

def run_volume_shocker(df):
    if len(df) < 20:
        return False
    vol_sma = df["volume"].rolling(10).mean()
    last, prev = df.iloc[-1], df.iloc[-2]
    return (
        last["volume"] > 5 * vol_sma.iloc[-1]
        and prev["close"] * 0.95 <= last["close"] <= prev["close"] * 1.05
    )

def run_nrb_7(df):
    if len(df) < 20:
        return None
    base = df.iloc[-7]
    inside = df.iloc[-6:-1]
    last = df.iloc[-1]
    base_high, base_low = base["high"], base["low"]

    cond_high_low = inside["high"].max() <= base_high and inside["low"].min() >= base_low
    cond_open_close = (
        inside["open"].max() <= base_high
        and inside["open"].min() >= base_low
        and inside["close"].max() <= base_high
        and inside["close"].min() >= base_low
    )

    if not (cond_high_low and cond_open_close):
        return None

    avg_vol = df["volume"].rolling(10).mean().iloc[-2]
    if last["volume"] < 1.5 * avg_vol:
        return None

    if last["close"] > base_high:
        return "NRB-7 Bullish Breakout + Volume"
    if last["close"] < base_low:
        return "NRB-7 Bearish Breakdown + Volume"
    return None

def run_counter_attack(df):
    if len(df) < 2:
        return None
    prev, curr = df.iloc[-2], df.iloc[-1]
    mid = (prev["open"] + prev["close"]) / 2
    if prev["close"] < prev["open"] and curr["close"] > curr["open"]:
        if curr["open"] < prev["close"] and curr["close"] >= mid:
            return "Bullish"
    if prev["close"] > prev["open"] and curr["close"] < curr["open"]:
        if curr["open"] > prev["close"] and curr["close"] <= mid:
            return "Bearish"
    return None

def run_breakaway_gap(df):
    if len(df) < 50:
        return None
    df = df.copy()
    df["EMA20"] = talib.EMA(df["close"], 20)
    df["EMA50"] = talib.EMA(df["close"], 50)
    prev, curr = df.iloc[-2], df.iloc[-1]

    if curr["open"] > prev["high"] * 1.005 and curr["low"] > prev["high"]:
        if curr["EMA20"].iloc[-1] < curr["EMA50"].iloc[-1]:
            return "Bullish Breakaway Gap"
    if curr["open"] < prev["low"] * 0.995 and curr["high"] < prev["low"]:
        if curr["EMA20"].iloc[-1] > curr["EMA50"].iloc[-1]:
            return "Bearish Breakaway Gap"
    return None

def run_rsi_adx(df):
    if len(df) < 20:
        return None
    rsi = talib.RSI(df["close"], 14).iloc[-1]
    adx = talib.ADX(df["high"], df["low"], df["close"], 14).iloc[-1]
    if adx > 50 and rsi < 20:
        return "Bullish Reversal"
    if adx > 50 and rsi > 80:
        return "Probable Bearish Reversal"
    return None

def run_macd_market_pulse(df):
    if len(df) < 30:
        return None
    macd, signal, _ = talib.MACD(df["close"], 12, 26, 9)
    m, s = macd.iloc[-1], signal.iloc[-1]
    pm = macd.iloc[-2]

    if m > 0 and m > s and m > pm:
        return "Strong Bullish"
    if m > 0 and m > s and m < pm:
        return "Bullish Cooling"
    if m > 0 and m < s and m > pm:
        return "Bullish Reversal Watch"
    if m > 0 and m < s and m < pm:
        return "Weak Bullish"
    if m < 0 and m > s and m > pm:
        return "Bearish Reversal Watch"
    if m < 0 and m > s and m < pm:
        return "Weak Bearish"
    if m < 0 and m < s and m > pm:
        return "Bearish Recovery Attempt"
    if m < 0 and m < s and m < pm:
        return "Strong Bearish"
    return None

def run_macd_normal_divergence(df, lookback=30):
    if len(df) < lookback:
        return None
    macd, _, _ = talib.MACD(df["close"], 12, 26, 9)
    price_low1 = df["low"].iloc[-lookback:-15].min()
    price_low2 = df["low"].iloc[-15:].min()
    macd_low1 = macd.iloc[-lookback:-15].min()
    macd_low2 = macd.iloc[-15:].min()

    if price_low2 < price_low1 and macd_low2 > macd_low1:
        return "Bullish ND"

    price_high1 = df["high"].iloc[-lookback:-15].max()
    price_high2 = df["high"].iloc[-15:].max()
    macd_high1 = macd.iloc[-lookback:-15].max()
    macd_high2 = macd.iloc[-15:].max()

    if price_high2 > price_high1 and macd_high2 < macd_high1:
        return "Bearish ND"
    return None

def run_trend_alignment(df):
    if len(df) < 100:
        return None
    ema20 = talib.EMA(df["close"], 20).iloc[-1]
    ema50 = talib.EMA(df["close"], 50).iloc[-1]
    ema100 = talib.EMA(df["close"], 100).iloc[-1]

    if ema20 > ema50 > ema100:
        return "Strong Uptrend"
    if ema20 < ema50 < ema100:
        return "Strong Downtrend"
    return None

def run_pullback_to_ema(df):
    if len(df) < 60:
        return None
    ema20 = talib.EMA(df["close"], 20).iloc[-1]
    ema50 = talib.EMA(df["close"], 50).iloc[-1]
    last = df.iloc[-1]

    if ema20 > ema50:
        if last["low"] <= ema20 and last["close"] > ema20:
            return "Bullish EMA Pullback"
    if ema20 < ema50:
        if last["high"] >= ema20 and last["close"] < ema20:
            return "Bearish EMA Pullback"
    return None

def run_confluence_setup(df):
    if len(df) < 60:
        return None
    rsi = talib.RSI(df["close"], 14).iloc[-1]
    macd, sig, _ = talib.MACD(df["close"], 12, 26, 9)
    ema20 = talib.EMA(df["close"], 20).iloc[-1]
    ema50 = talib.EMA(df["close"], 50).iloc[-1]

    if rsi > 50 and macd.iloc[-1] > sig.iloc[-1] and ema20 > ema50:
        return "Bullish Confluence"
    if rsi < 50 and macd.iloc[-1] < sig.iloc[-1] and ema20 < ema50:
        return "Bearish Confluence"
    return None

def run_macd_hook_up(df):
    if len(df) < 35:
        return None
    macd, signal, hist = talib.MACD(df["close"], 12, 26, 9)
    if (
        macd.iloc[-1] > 0
        and macd.iloc[-1] > signal.iloc[-1]
        and macd.iloc[-2] > signal.iloc[-2]
        and macd.iloc[-2] < macd.iloc[-3]
        and macd.iloc[-1] > macd.iloc[-2]
        and hist.iloc[-1] > hist.iloc[-2]
    ):
        return "MACD Hook Up"
    return None

def run_macd_hook_down(df):
    if len(df) < 35:
        return None
    macd, signal, hist = talib.MACD(df["close"], 12, 26, 9)
    if (
        macd.iloc[-1] < 0
        and macd.iloc[-1] < signal.iloc[-1]
        and macd.iloc[-2] < signal.iloc[-2]
        and macd.iloc[-2] > macd.iloc[-3]
        and macd.iloc[-1] < macd.iloc[-2]
        and hist.iloc[-1] < hist.iloc[-2]
    ):
        return "MACD Hook Down"
    return None

def run_ema50_stoch_oversold(df):
    if len(df) < 50:
        return None
    ema50 = talib.EMA(df["close"], 50).iloc[-1]
    slowk, slowd = talib.STOCH(
        df["high"], df["low"], df["close"], fastk_period=14, slowk_period=3, slowd_period=3
    )
    price = df["close"].iloc[-1]
    near_ema = abs(price - ema50) / ema50 <= 0.005
    stoch_cross = (
        slowk.iloc[-2] < slowd.iloc[-2]
        and slowk.iloc[-1] > slowd.iloc[-1]
        and slowk.iloc[-1] < 20
    )
    if near_ema and stoch_cross:
        return "EMA50 + Stoch Oversold Buy"
    return None

def run_kdj(df, period=9, signal=3):
    low_min = df["low"].rolling(period).min()
    high_max = df["high"].rolling(period).max()
    rng = (high_max - low_min).replace(0, np.nan)
    rsv = 100 * (df["close"] - low_min) / rng
    rsv = rsv.clip(lower=0, upper=100)

    def bcwsma(series, length):
        out = []
        for i, val in enumerate(series):
            if i == 0 or np.isnan(val):
                out.append(val)
            else:
                out.append((val + (length - 1) * out[-1]) / length)
        return pd.Series(out, index=series.index)

    pK = bcwsma(rsv, signal)
    pD = bcwsma(pK, signal)
    pJ = 3 * pK - 2 * pD
    return pK, pD, pJ

def run_kdj_buy(df):
    if len(df) < 20:
        return None
    pK, pD, pJ = run_kdj(df)
    if pd.isna(pD.iloc[-1]) or pd.isna(pJ.iloc[-1]):
        return None
    crossed_up = (pJ.iloc[-2] < pD.iloc[-2]) and (pJ.iloc[-1] > pD.iloc[-1])
    oversold = (pD.iloc[-1] < 30) and (pJ.iloc[-1] < 30)
    if crossed_up and oversold:
        return "KDJ BUY (J↑D oversold)"
    return None

def run_kdj_sell(df):
    if len(df) < 20:
        return None
    pK, pD, pJ = run_kdj(df)
    if pd.isna(pD.iloc[-1]) or pd.isna(pJ.iloc[-1]):
        return None
    crossed_down = (pJ.iloc[-2] > pD.iloc[-2]) and (pJ.iloc[-1] < pD.iloc[-1])
    overbought = (pD.iloc[-1] > 70) and (pJ.iloc[-1] > 70)
    if crossed_down and overbought:
        return "KDJ SELL (J↓D overbought)"
    return None

def run_macd_nd_filtered(df):
    nd = run_macd_normal_divergence(df)
    if nd:
        return {
            "Signal": "Divergence Alert",
            "Divergence": nd
        }
    return None

SCANNERS = {
    "RSI Market Pulse": lambda df: {
        "Signal": "Monitor",
        "RSI": run_rsi_market_pulse(df)[0],
        "Zone": run_rsi_market_pulse(df)[1],
    },
    "Volume Shocker": lambda df: {
        "Signal": "BUY" if run_volume_shocker(df) else "Neutral",
        "Setup": "High Vol Expansion" if run_volume_shocker(df) else None
    },
    "NRB-7 breakout": lambda df: {
        "Signal": "BUY/SELL" if run_nrb_7(df) else "Neutral",
        "Setup": run_nrb_7(df)
    },
    "Counter Attack Pattern": lambda df: {
        "Signal": run_counter_attack(df) or "Neutral"
    },
    "Breakaway Gap": lambda df: {
        "Signal": "Alert",
        "Setup": run_breakaway_gap(df)
    },
    "RSI + ADX Extremes": lambda df: {
        "Signal": "Reversal Watch",
        "Setup": run_rsi_adx(df)
    },
    "MACD Market Pulse": lambda df: {
        "Signal": "Monitor",
        "Trend": run_macd_market_pulse(df)
    },
    "MACD Normal Divergence": lambda df: run_macd_nd_filtered(df),
    "Trend Alignment": lambda df: {
        "Signal": "Uptrend/Downtrend",
        "Trend": run_trend_alignment(df)
    },
    "Pullback to EMA": lambda df: {
        "Signal": "Pullback Check",
        "Setup": run_pullback_to_ema(df)
    },
    "Confluence": lambda df: {
        "Signal": "Confluence Detected",
        "Setup": run_confluence_setup(df)
    },
    "MACD Hook Up": lambda df: {
        "Signal": "BUY" if run_macd_hook_up(df) else "Neutral"
    },
    "MACD Hook Down": lambda df: {
        "Signal": "SELL" if run_macd_hook_down(df) else "Neutral"
    },
    "EMA50 + Stochastic": lambda df: {
        "Signal": "BUY" if run_ema50_stoch_oversold(df) else "Neutral"
    },
    "KDJ Cross Buy": lambda df: {
        "Signal": "BUY" if run_kdj_buy(df) else "Neutral"
    },
    "KDJ Cross Sell": lambda df: {
        "Signal": "SELL" if run_kdj_sell(df) else "Neutral"
    }
}

def extract_grid_cell_value(scanner_name, res):
    if not res:
        return ""
    if scanner_name == "Volume Shocker":
        return "High Vol Expansion" if res.get("Signal") == "BUY" else ""
    elif scanner_name == "NRB-7 breakout":
        return res.get("Setup") or ""
    elif scanner_name == "Counter Attack Pattern":
        sig = res.get("Signal")
        return sig if sig != "Neutral" else ""
    elif scanner_name in ["Breakaway Gap", "RSI + ADX Extremes", "Pullback to EMA", "Confluence"]:
        return res.get("Setup") or ""
    elif scanner_name in ["MACD Market Pulse", "Trend Alignment"]:
        return res.get("Trend") or ""
    elif scanner_name == "MACD Normal Divergence":
        return res.get("Divergence") or ""
    elif scanner_name in ["MACD Hook Up", "MACD Hook Down", "EMA50 + Stochastic", "KDJ Cross Buy", "KDJ Cross Sell"]:
        sig = res.get("Signal")
        return sig if sig != "Neutral" else ""
    elif scanner_name == "RSI Market Pulse":
        return res.get("Zone") or ""
    return str(res.get("Signal", ""))

# ==============================================================================
# 4. BATCH PROCESSING ENGINE (UPDATED FOR JSON FILES)
# ==============================================================================
def process_timeframe(folder_name, output_name, date_str):
    folder_path = os.path.join(BASE_PATH, folder_name)
    if not os.path.exists(folder_path):
        logger.warning(f"Skipping {folder_name}: Directory not found.")
        return None, [], pd.DataFrame(), None

    # UPDATED FILE EXTENSION TO .JSON
    files = [f for f in os.listdir(folder_path) if f.endswith(".json")]
    if not files:
        logger.warning(f"Skipping {folder_name}: No json files found.")
        return None, [], pd.DataFrame(), None

    logger.info(f"Scanning {len(files)} symbols in {folder_name}...")
    sheets_data = {scanner_name: [] for scanner_name in SCANNERS.keys()}
    grid_rows = []
    sample_df_dict = {}

    for f in files:
        sym = f.replace(".json", "")
        try:
            # UPDATED FOR READING JSON DATA
            file_filepath = os.path.join(folder_path, f)
            df = pd.read_json(file_filepath)
            
            # Normalize column names to lowercase to ensure compatibility with ta-lib
            df.columns = [str(c).lower() for c in df.columns]

            if df.empty or len(df) < 50:
                continue

            grid_stock_row = {"Symbol": sym}
            sample_df_dict[sym] = df

            for scanner_name, scanner_fn in SCANNERS.items():
                try:
                    res = scanner_fn(df)
                    grid_stock_row[scanner_name] = extract_grid_cell_value(scanner_name, res)
                    
                    if res:
                        row = {col: "" for col in SAFE_COLS}
                        row["Symbol"] = sym
                        row["TV_Link"] = make_tradingview_link(sym)
                        
                        for k, v in res.items():
                            if k in row and v is not None:
                                row[k] = v
                                
                        if any(row[col] not in ["", "Neutral", None] for col in ["Signal", "Setup", "Divergence", "Trend"]):
                            sheets_data[scanner_name].append(row)
                except Exception as e:
                    logger.debug(f"Failed to scan {sym} with {scanner_name}: {e}")
                    
            grid_rows.append(grid_stock_row)
                        
        except Exception as e:
            logger.error(f"Error loading file {f}: {e}")

    excel_filename = f"{output_name}_{date_str}.xlsx"
    excel_filepath = os.path.join(OUTPUT_DIR, excel_filename)
    
    with pd.ExcelWriter(excel_filepath, engine="openpyxl") as writer:
        for scanner_name, rows in sheets_data.items():
            df_out = pd.DataFrame(rows) if rows else pd.DataFrame(columns=SAFE_COLS)
            if df_out.empty:
                df_out = pd.DataFrame([["No scanner alerts detected for this interval", ""] + [""] * 10], columns=SAFE_COLS)
            df_out.to_excel(writer, sheet_name=scanner_name[:30], index=False)

    logger.info(f"Successfully generated: {excel_filepath}")
    df_grid_tf = pd.DataFrame(grid_rows) if grid_rows else pd.DataFrame(columns=["Symbol"] + list(SCANNERS.keys()))
    return excel_filepath, sheets_data.get("MACD Normal Divergence", []), df_grid_tf, sample_df_dict

# ==============================================================================
# 5. EXCLUSIVE HTML DASHBOARD BLOCK BUILDER
# ==============================================================================
def build_html_dashboard(grid_dfs, date_str):
    """
    Generates a clean dashboard containing only the Top Picks Table and the MACD 2-line chart.
    """
    total_stocks_tracked = 0
    top_picks_list = []
    
    for tf, df in grid_dfs.items():
        if df.empty:
            continue
            
        total_stocks_tracked = max(total_stocks_tracked, len(df))
        
        for _, row in df.iterrows():
            conditions = [
                "Bullish Confluence" in str(row["Confluence"]),
                "High Vol Expansion" in str(row["Volume Shocker"]),
                "Bullish ND" in str(row["MACD Normal Divergence"]),
                "MACD Hook Up" in str(row["MACD Hook Up"])
            ]
            if any(conditions) and len(top_picks_list) < 8:
                reasons = []
                if conditions[0]: reasons.append("Confluence")
                if conditions[1]: reasons.append("Vol Expansion")
                if conditions[2]: reasons.append("MACD Divergence")
                if conditions[3]: reasons.append("MACD Hook Up")
                
                pick_info = {
                    "symbol": row["Symbol"],
                    "tf": tf,
                    "reason": " + ".join(reasons),
                    "link": make_tradingview_link(row["Symbol"])
                }
                if pick_info not in top_picks_list:
                    top_picks_list.append(pick_info)

    # Build Top Picks Table rows
    top_picks_rows = ""
    if top_picks_list:
        for pick in top_picks_list:
            top_picks_rows += f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 10px; font-weight: bold; color: #1e3a8a;">{pick['symbol']}</td>
                <td style="padding: 10px;"><span style="background-color: #dbeafe; color: #1e40af; padding: 2px 6px; border-radius: 4px; font-size: 11px;">{pick['tf']}</span></td>
                <td style="padding: 10px; color: #475569; font-size: 12px;">✨ {pick['reason']}</td>
                <td style="padding: 10px;"><a href="{pick['link']}" style="color: #3b82f6; text-decoration: none; font-weight: bold;" target="_blank">Chart ↗</a></td>
            </tr>
            """
    else:
        top_picks_rows = """<tr><td colspan="4" style="padding: 15px; text-align: center; color: #94a3b8;">No immediate breakthrough setups detected today. Check full sheets.</td></tr>"""

    # Dashboard Email Body
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>FNO Executive Market Dashboard</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f4f6f9; margin: 0; padding: 20px; color: #334155;">
        <div style="max-width: 700px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);">
            
            <!-- Dashboard Banner Header -->
            <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); padding: 25px; color: #ffffff; text-align: center;">
                <h1 style="margin: 0; font-size: 24px; font-weight: 700; letter-spacing: -0.5px;">📊 FNO Automated Scanner Dashboard</h1>
                <p style="margin: 6px 0 0 0; opacity: 0.9; font-size: 14px;">Market Analytics Summary &bull; {date_str}</p>
            </div>
            
            <!-- Quick Status Cards -->
            <div style="padding: 20px; background-color: #f8fafc; display: flex; justify-content: space-between; border-bottom: 1px solid #e2e8f0; gap: 10px;">
                <div style="background-color: white; padding: 10px 15px; border-radius: 6px; border-left: 4px solid #3b82f6; width: 45%;">
                    <div style="font-size: 11px; color: #64748b; font-weight: bold; text-transform: uppercase;">Stocks Monitored</div>
                    <div style="font-size: 20px; font-weight: bold; color: #1e293b;">{total_stocks_tracked} Symbols</div>
                </div>
                <div style="background-color: white; padding: 10px 15px; border-radius: 6px; border-left: 4px solid #10b981; width: 45%;">
                    <div style="font-size: 11px; color: #64748b; font-weight: bold; text-transform: uppercase;">Pipeline Run Status</div>
                    <div style="font-size: 20px; font-weight: bold; color: #10b981;">SUCCESS ✅</div>
                </div>
            </div>

            <div style="padding: 20px;">
                <!-- Section: Top High Probability Picks -->
                <h2 style="font-size: 16px; color: #1e3a8a; text-transform: uppercase; margin-top: 0; margin-bottom: 12px; border-left: 4px solid #1e3a8a; padding-left: 8px;">⭐ Top Picks / Technical Confluences</h2>
                <table style="width: 100%; border-collapse: collapse; text-align: left; margin-bottom: 25px; background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; overflow: hidden;">
                    <thead>
                        <tr style="background-color: #f1f5f9; color: #475569; font-size: 13px;">
                            <th style="padding: 10px;">Stock</th>
                            <th style="padding: 10px;">Interval</th>
                            <th style="padding: 10px;">Matching Technical Triggers</th>
                            <th style="padding: 10px;">TradingView</th>
                        </tr>
                    </thead>
                    <tbody style="font-size: 13px;">
                        {top_picks_rows}
                    </tbody>
                </table>

                <!-- Section: Visual MACD 2-Line Graph -->
                <h2 style="font-size: 16px; color: #1e3a8a; text-transform: uppercase; margin-bottom: 12px; border-left: 4px solid #1e3a8a; padding-left: 8px;">📈 Top Technical Setup MACD Pulse</h2>
                <div style="text-align: center; background-color: #f8fafc; padding: 15px; border-radius: 8px; border: 1px solid #e2e8f0;">
                    <img src="cid:macd_chart" alt="MACD 2 Line Graph Trend View" style="max-width: 100%; height: auto; border-radius: 4px;" />
                </div>
                
                <!-- Footer Info -->
                <div style="margin-top: 25px; padding-top: 15px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8; text-align: center;">
                    <p>This automated email dashboard tracks key structural indicators across multiple custom target windows.<br/>
                    Please refer to the attached separate Excel documents for comprehensive scanning row matrices.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html_body, top_picks_list

# ==============================================================================
# 6. COMMUNICATIONS (EMAIL & TELEGRAM MODULES)
# ==============================================================================
def send_email_with_dashboard(file_paths, chart_path, date_str, html_dashboard_content):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        logger.error("Email credentials missing. Skipping email dispatch.")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"FNO Executive Stock Scanner Report - {date_str}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(RECIPIENTS)
    
    if "BCC_RECIPIENTS" in globals() and BCC_RECIPIENTS:
        msg["Bcc"] = ", ".join(BCC_RECIPIENTS)

    msg.set_content(f"Please view this email via an HTML-compatible client to see the automated market dashboard summary for {date_str}.")
    msg.add_alternative(html_dashboard_content, subtype="html")

    # Inject inline MACD Chart
    if chart_path and os.path.exists(chart_path):
        with open(chart_path, "rb") as img_f:
            msg.get_payload()[1].add_related(
                img_f.read(),
                maintype="image",
                subtype="png",
                cid="macd_chart"
            )

    # Attach Excel files
    for path in file_paths:
        if not os.path.exists(path):
            continue
            
        ctype, encoding = mimetypes.guess_type(path)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        
        with open(path, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype=maintype,
                subtype=subtype,
                filename=os.path.basename(path)
            )

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        logger.info("Notification email dashboard dispatched successfully.")
        return True
    except Exception as e:
        logger.error(f"SMTP Email Delivery failed: {e}")
        return False

def send_telegram_notification(date_str, report_count, total_scanners):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        logger.warning("Telegram details are unconfigured. Skipping Telegram alert.")
        return

    text = (
        f"✅ *FNO Scanner Completed*\n\n"
        f"📅 *Date :* {date_str}\n\n"
        f"*Generated Reports:*\n"
        f"✔ 15 Min\n"
        f"✔ Hourly\n"
        f"✔ Daily\n"
        f"✔ Weekly\n"
        f"✔ Monthly\n"
        f"✔ Comprehensive Summary Matrix Grid\n\n"
        f"📈 *Total Scanners :* {total_scanners}\n\n"
        f"✉ *Status :* {report_count} Reports & Dashboard mailed successfully."
    )

    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown"
            }).encode("utf-8")
            
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req) as response:
                response.read()
            logger.info(f"Telegram notification sent to Chat ID: {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message to {chat_id}: {e}")

# ==============================================================================
# 7. MAIN CONTROLLER PIPELINE
# ==============================================================================
def main():
    start_time = datetime.now()
    date_str = start_time.strftime("%d %b %Y")
    logger.info(f"=== Starting NSE Batch Scanner Pipeline ({date_str}) ===")

    generated_files = []
    macd_divergences_by_tf = {}  
    grid_dataframes_by_tf = {} 
    full_historical_dfs_by_tf = {}

    for tf_key, (folder_name, output_name) in TIMEFRAME_FOLDERS.items():
        filepath, macd_rows, df_grid_tf, sample_df_dict = process_timeframe(folder_name, output_name, date_str)
        if filepath:
            generated_files.append(filepath)
            macd_divergences_by_tf[tf_key] = macd_rows
            if not df_grid_tf.empty:
                grid_dataframes_by_tf[tf_key] = df_grid_tf
                full_historical_dfs_by_tf[tf_key] = sample_df_dict

    # Consolidated matrix grid
    if grid_dataframes_by_tf:
        summary_matrix_filename = f"Scanner Summary Matrix_{date_str}.xlsx"
        summary_matrix_filepath = os.path.join(OUTPUT_DIR, summary_matrix_filename)
        
        with pd.ExcelWriter(summary_matrix_filepath, engine="openpyxl") as writer:
            for tf_key, df_matrix in grid_dataframes_by_tf.items():
                cols_order = ["Symbol"] + [c for c in df_matrix.columns if c != "Symbol"]
                df_matrix = df_matrix[cols_order]
                df_matrix.to_excel(writer, sheet_name=tf_key, index=False)
                
        logger.info(f"Successfully generated full mapping Summary Matrix: {summary_matrix_filepath}")
        generated_files.append(summary_matrix_filepath)

    # Combined MACD Divergences report
    if macd_divergences_by_tf:
        combined_macd_filename = f"MACD Normal Divergences_{date_str}.xlsx"
        combined_macd_filepath = os.path.join(OUTPUT_DIR, combined_macd_filename)
        
        with pd.ExcelWriter(combined_macd_filepath, engine="openpyxl") as writer:
            for tf_key, rows in macd_divergences_by_tf.items():
                df_out = pd.DataFrame(rows) if rows else pd.DataFrame(columns=SAFE_COLS)
                if df_out.empty:
                    df_out = pd.DataFrame([["No scanner alerts detected for this interval", ""] + [""] * 10], columns=SAFE_COLS)
                df_out.to_excel(writer, sheet_name=tf_key, index=False)
                
        logger.info(f"Successfully generated combined MACD report: {combined_macd_filepath}")
        generated_files.append(combined_macd_filepath)

    if not generated_files:
        logger.error("No reports were generated. Aborting email and Telegram alerts.")
        return

    # Build Dashboard
    html_dashboard_content, top_picks_list = build_html_dashboard(grid_dataframes_by_tf, date_str)

    # Generate MACD chart
    chart_path = os.path.join(OUTPUT_DIR, "macd_trend_graph.png")
    chart_created = False
    
    if top_picks_list:
        target_pick = top_picks_list[0]
        sym = target_pick["symbol"]
        tf = target_pick["tf"]
        
        if tf in full_historical_dfs_by_tf and sym in full_historical_dfs_by_tf[tf]:
            stock_df = full_historical_dfs_by_tf[tf][sym]
            if len(stock_df) >= 35:
                macd, signal, _ = talib.MACD(stock_df["close"], 12, 26, 9)
                
                plt.figure(figsize=(7, 3.5))
                plt.plot(macd.index[-40:], macd.iloc[-40:], label="MACD Line", color="#2563eb", linewidth=2)
                plt.plot(signal.index[-40:], signal.iloc[-40:], label="Signal Line", color="#ea580c", linewidth=1.5, linestyle="--")
                plt.axhline(0, color="#94a3b8", linestyle=":", linewidth=1)
                
                plt.title(f"MACD 2-Line Indicator ({sym} - {tf})", fontsize=12, fontweight="bold", color="#1e293b")
                plt.legend(loc="upper left", frameon=True, facecolor="#ffffff", edgecolor="#e2e8f0")
                plt.grid(True, linestyle=":", alpha=0.5)
                plt.tight_layout()
                
                plt.savefig(chart_path, dpi=120)
                plt.close()
                chart_created = True
                
    if not chart_created:
        plt.figure(figsize=(7, 3.5))
        plt.text(0.5, 0.5, "No immediate breakthrough setups detected.\nShowing flat trend chart baseline.", 
                 ha="center", va="center", color="#64748b", fontsize=11)
        plt.axhline(0, color="#94a3b8", linestyle=":", linewidth=1)
        plt.title("MACD Baseline Monitor Overview", fontsize=12, fontweight="bold", color="#1e293b")
        plt.tight_layout()
        plt.savefig(chart_path, dpi=120)
        plt.close()

    # Send Communications
    mail_success = send_email_with_dashboard(generated_files, chart_path, date_str, html_dashboard_content)
    
    if mail_success:
        send_telegram_notification(
            date_str=date_str, 
            report_count=len(generated_files), 
            total_scanners=len(SCANNERS)
        )

    end_time = datetime.now()
    duration = end_time - start_time
    logger.info(f"=== Pipeline completed successfully in {duration.total_seconds():.2f} seconds ===")

if __name__ == "__main__":
    main()
