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
logger = logging.getLogger("NSE_Divergence_Scanner")

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

BASE_PATH = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
OUTPUT_DIR = os.path.join(BASE_PATH, "Output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Updated Folder Names (Removed underscore: stockdata_*)
TIMEFRAME_FOLDERS = {
    "15 Min": ("stockdata_15", "15 Min Scan"),
    "Hourly": ("stockdata_1H", "Hourly Scan"),
    "Daily": ("stockdata_D", "Daily Scan"),
    "Weekly": ("stockdata_W", "Weekly Scan"),
    "Monthly": ("stockdata_M", "Monthly Scan"),
}

# Higher-Timeframe (HTF) to Lower-Timeframe (LTF) Pairings
HTF_LTF_MAP = [
    ("Hourly", "15 Min"),
    ("Daily", "Hourly"),
    ("Weekly", "Daily"),
    ("Monthly", "Weekly")
]

SAFE_COLS = ["Symbol", "Divergence", "Close", "TV_Link"]

def make_tradingview_link(sym: str) -> str:
    return f"https://in.tradingview.com/chart/LqUZraZ9/?symbol=NSE%3A{sym}"

# ==============================================================================
# 3. DIVERGENCE DETECTION LOGIC (4 TYPES)
# ==============================================================================
def detect_macd_divergence(df, lookback=30):
    """
    Detects 4 types of MACD Divergences:
    1. Bearish Divergence (ND): Price Higher High, MACD Lower High
    2. Bullish Divergence (ND): Price Lower Low, MACD Higher Low
    3. Reverse Bullish Divergence (RD): Price Higher Low, MACD Lower Low
    4. Reverse Bearish Divergence (RD): Price Lower High, MACD Higher High
    """
    if len(df) < lookback:
        return None

    macd, _, _ = talib.MACD(df["close"], 12, 26, 9)
    
    # Segment windows: Window 1 (Older), Window 2 (Recent)
    p_high1 = df["high"].iloc[-lookback:-15].max()
    p_high2 = df["high"].iloc[-15:].max()
    m_high1 = macd.iloc[-lookback:-15].max()
    m_high2 = macd.iloc[-15:].max()

    p_low1 = df["low"].iloc[-lookback:-15].min()
    p_low2 = df["low"].iloc[-15:].min()
    m_low1 = macd.iloc[-lookback:-15].min()
    m_low2 = macd.iloc[-15:].min()

    # 1. Bearish Normal Divergence (ND)
    if p_high2 > p_high1 and m_high2 < m_high1:
        return "Bearish ND"

    # 2. Bullish Normal Divergence (ND)
    if p_low2 < p_low1 and m_low2 > m_low1:
        return "Bullish ND"

    # 3. Reverse Bullish Divergence (RD) / Hidden Bullish
    if p_low2 > p_low1 and m_low2 < m_low1:
        return "Bullish RD"

    # 4. Reverse Bearish Divergence (RD) / Hidden Bearish
    if p_high2 < p_high1 and m_high2 > m_high1:
        return "Bearish RD"

    return None

# ==============================================================================
# 4. BATCH PROCESSING ENGINE FOR INDIVIDUAL TIMEFRAMES
# ==============================================================================
def process_timeframe(folder_name):
    folder_path = os.path.join(BASE_PATH, folder_name)
    if not os.path.exists(folder_path):
        logger.warning(f"Skipping {folder_name}: Directory not found.")
        return {}, {}

    # Updated file extension filter to .json
    files = [f for f in os.listdir(folder_path) if f.endswith(".json")]
    if not files:
        logger.warning(f"Skipping {folder_name}: No json files found.")
        return {}, {}

    logger.info(f"Scanning {len(files)} symbols in {folder_name}...")
    divergence_results = {}
    sample_df_dict = {}

    for f in files:
        sym = f.replace(".json", "")
        try:
            # Updated file reader to pd.read_json()
            df = pd.read_json(os.path.join(folder_path, f))
            if df.empty or len(df) < 50:
                continue

            div_type = detect_macd_divergence(df)
            sample_df_dict[sym] = df

            if div_type:
                divergence_results[sym] = {
                    "Symbol": sym,
                    "Divergence": div_type,
                    "Close": round(df["close"].iloc[-1], 2),
                    "TV_Link": make_tradingview_link(sym)
                }

        except Exception as e:
            logger.error(f"Error loading file {f}: {e}")

    return divergence_results, sample_df_dict

# ==============================================================================
# 5. MULTI-TIMEFRAME BUCKET ANALYTICS ENGINE (BUY/SELL RECOMMENDATIONS)
# ==============================================================================
def generate_analytics_data(tf_divergences):
    """
    Evaluates alignment between HTF and LTF to generate Buy/Sell Recommendations
    matching the HTPL Dashboard layout.
    """
    analytics_rows = []

    for htf, ltf in HTF_LTF_MAP:
        htf_data = tf_divergences.get(htf, {})
        ltf_data = tf_divergences.get(ltf, {})

        # Find symbols detected in both HTF and LTF
        common_symbols = set(htf_data.keys()).intersection(set(ltf_data.keys()))

        for sym in common_symbols:
            htf_div = htf_data[sym]["Divergence"]
            ltf_div = ltf_data[sym]["Divergence"]

            recommendation = None
            remark = ""

            # Bucket 1: HTF Bullish ND + LTF Bullish ND -> STRONG BUY
            if htf_div == "Bullish ND" and ltf_div == "Bullish ND":
                recommendation = "STRONG BUY"
                remark = f"{sym}: HTF {htf} Bullish ND and LTF {ltf} Bullish ND (Strong Reversal Confluence)"

            # Bucket 2: HTF Bullish RD + LTF Bullish ND -> BUY
            elif htf_div == "Bullish RD" and ltf_div == "Bullish ND":
                recommendation = "BUY"
                remark = f"{sym}: HTF {htf} Bullish RD and LTF {ltf} Bullish ND (Trend Continuation with Entry Signal)"

            # Bucket 3: HTF Bearish ND + LTF Bearish ND -> STRONG SELL
            elif htf_div == "Bearish ND" and ltf_div == "Bearish ND":
                recommendation = "STRONG SELL"
                remark = f"{sym}: HTF {htf} Bearish ND and LTF {ltf} Bearish ND (Strong Distribution Signal)"

            # Bucket 4: HTF Bearish RD + LTF Bearish ND -> SELL
            elif htf_div == "Bearish RD" and ltf_div == "Bearish ND":
                recommendation = "SELL"
                remark = f"{sym}: HTF {htf} Bearish RD and LTF {ltf} Bearish ND (Downtrend Continuation Signal)"

            if recommendation:
                pairing_signals = f"{htf} ({htf_div}) / {ltf} ({ltf_div})"
                analytics_rows.append({
                    "Stock": sym,
                    "Pairing & Signals": pairing_signals,
                    "Recommendation": recommendation,
                    "Remarks": remark,
                    "Chart": make_tradingview_link(sym)
                })

    return pd.DataFrame(analytics_rows)

# ==============================================================================
# 6. HTML EMAIL DASHBOARD GENERATOR (MATCHING DASHBOARD DESIGN)
# ==============================================================================
def build_html_dashboard(analytics_df, date_str):
    table_rows = ""

    if not analytics_df.empty:
        for _, row in analytics_df.iterrows():
            rec = row['Recommendation']
            
            # Text Color & Styling based on Buy/Sell
            if rec == "STRONG BUY":
                rec_style = "color: #059669; font-weight: bold;"
            elif rec == "BUY":
                rec_style = "color: #10b981; font-weight: bold;"
            elif rec == "STRONG SELL":
                rec_style = "color: #dc2626; font-weight: bold;"
            elif rec == "SELL":
                rec_style = "color: #ef4444; font-weight: bold;"
            else:
                rec_style = "color: #475569;"

            table_rows += f"""
            <tr style="border-bottom: 1px solid #e2e8f0;">
                <td style="padding: 12px; font-weight: bold; color: #0f172a; font-size: 13px;">{row['Stock']}</td>
                <td style="padding: 12px; color: #334155; font-size: 12px;">{row['Pairing & Signals']}</td>
                <td style="padding: 12px; {rec_style} font-size: 12px;">{row['Recommendation']}</td>
                <td style="padding: 12px; color: #475569; font-size: 12px;">{row['Remarks']}</td>
                <td style="padding: 12px;"><a href="{row['Chart']}" style="color: #7e22ce; text-decoration: none; font-weight: bold; font-size: 12px;" target="_blank">Chart ↗</a></td>
            </tr>
            """
    else:
        table_rows = """<tr><td colspan="5" style="padding: 20px; text-align: center; color: #94a3b8; font-size: 13px;">No buy/sell recommendations generated today. Check individual timeframe sheets.</td></tr>"""

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; margin: 0; padding: 20px; color: #1e293b;">
        <div style="max-width: 900px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); border: 1px solid #e2e8f0;">
            
            <!-- Dashboard Title Header -->
            <div style="background-color: #f1f5f9; padding: 16px 20px; border-bottom: 1px solid #e2e8f0; display: flex; align-items: center;">
                <h2 style="margin: 0; font-size: 16px; color: #1e3a8a; font-weight: 700; text-transform: uppercase;">
                    🎯 HTPL DASHBOARD (BUY / SELL RECOMMENDATIONS)
                </h2>
            </div>
            
            <!-- Dashboard Table -->
            <div style="padding: 0;">
                <table style="width: 100%; border-collapse: collapse; text-align: left; background-color: #ffffff;">
                    <thead>
                        <tr style="background-color: #f8fafc; color: #64748b; font-size: 11px; text-transform: uppercase; border-bottom: 1px solid #e2e8f0;">
                            <th style="padding: 12px; width: 15%;">Stock</th>
                            <th style="padding: 12px; width: 28%;">Pairing & Signals</th>
                            <th style="padding: 12px; width: 17%;">Recommendation</th>
                            <th style="padding: 12px; width: 30%;">Remarks</th>
                            <th style="padding: 12px; width: 10%;">Chart</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>
            
            <!-- Footer -->
            <div style="padding: 12px 20px; background-color: #f8fafc; border-top: 1px solid #e2e8f0; text-align: right; color: #94a3b8; font-size: 11px;">
                Generated on {date_str} &bull; MACD Divergence Scanner Engine
            </div>
        </div>
    </body>
    </html>
    """
    return html_body

# ==============================================================================
# 7. COMMUNICATIONS MODULE
# ==============================================================================
def send_email_report(filepath, date_str, html_dashboard_content):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        logger.error("Email credentials missing. Skipping email dispatch.")
        return False

    msg = EmailMessage()
    msg["Subject"] = f"FNO:-HTPL Buy/Sell Recommendations Dashboard - {date_str}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(RECIPIENTS)
    
    if "BCC_RECIPIENTS" in globals() and BCC_RECIPIENTS:
        msg["Bcc"] = ", ".join(BCC_RECIPIENTS)

    msg.set_content("Please view this email via an HTML-compatible email client.")
    msg.add_alternative(html_dashboard_content, subtype="html")

    if filepath and os.path.exists(filepath):
        ctype, encoding = mimetypes.guess_type(filepath)
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, subtype = ctype.split("/", 1)
        
        with open(filepath, "rb") as f:
            msg.add_attachment(
                f.read(),
                maintype=maintype,
                subtype=subtype,
                filename=os.path.basename(filepath)
            )

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        logger.info("Email dashboard dispatched successfully.")
        return True
    except Exception as e:
        logger.error(f"SMTP Email Delivery failed: {e}")
        return False

def send_telegram_notification(date_str, report_generated):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_IDS:
        return

    text = (
        f"✅ *MACD Divergence Scanner Complete*\n\n"
        f"📅 *Date:* {date_str}\n"
        f"📊 *Timeframes Analyzed:* 15m, 1H, Daily, Weekly, Monthly\n"
        f"🎯 *Report Generated:* {'Yes' if report_generated else 'No'}\n\n"
        f"✉ *Status:* HTPL Dashboard Recommendations sent via email."
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
# 8. MAIN CONTROLLER PIPELINE
# ==============================================================================
def main():
    start_time = datetime.now()
    date_str = start_time.strftime("%d %b %Y")
    logger.info(f"=== Starting MACD Divergence Scanner Pipeline ({date_str}) ===")

    tf_divergences = {}

    # 1. Run Scans for each Timeframe
    for tf_key, (folder_name, _) in TIMEFRAME_FOLDERS.items():
        div_results, _ = process_timeframe(folder_name)
        tf_divergences[tf_key] = div_results

    # 2. Build Analytics Combinations Sheet with Buy/Sell Recommendations
    analytics_df = generate_analytics_data(tf_divergences)

    # 3. Create Excel Workbook containing 5 Timeframe Sheets + 1 Analytics Sheet
    output_filename = f"MACD_Divergence_Analysis_{date_str}.xlsx"
    output_filepath = os.path.join(OUTPUT_DIR, output_filename)

    with pd.ExcelWriter(output_filepath, engine="openpyxl") as writer:
        # Write Dashboard Summary Sheet first
        if not analytics_df.empty:
            analytics_df.to_excel(writer, sheet_name="HTPL Dashboard", index=False)
        else:
            empty_analytics = pd.DataFrame(columns=["Stock", "Pairing & Signals", "Recommendation", "Remarks", "Chart"])
            empty_analytics.to_excel(writer, sheet_name="HTPL Dashboard", index=False)

        # Write 5 Timeframe Sheets
        for tf_key in TIMEFRAME_FOLDERS.keys():
            results = list(tf_divergences.get(tf_key, {}).values())
            df_out = pd.DataFrame(results) if results else pd.DataFrame(columns=SAFE_COLS)
            df_out.to_excel(writer, sheet_name=tf_key, index=False)

    logger.info(f"Successfully generated consolidated Divergence Report: {output_filepath}")

    # 4. Generate Email Dashboard and Dispatch Communications
    html_dashboard = build_html_dashboard(analytics_df, date_str)
    email_success = send_email_report(output_filepath, date_str, html_dashboard)
    send_telegram_notification(date_str, email_success)

if __name__ == "__main__":
    main()
