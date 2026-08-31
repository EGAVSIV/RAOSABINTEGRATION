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

# New BASE_PATH (points to the parent repository root folder):
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
BASE_PATH = os.path.dirname(SCRIPT_DIR) # Moves 1 level up to the root folder
#BASE_PATH = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
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

def get_macd_crossover_state(df):
    """
    Determines current MACD crossover state:
    - PCO (Positive Cross Over): MACD line > Signal line
    - NCO (Negative Cross Over): MACD line <= Signal line
    """
    if len(df) < 35:
        return "N/A"

    macd, signal, _ = talib.MACD(df["close"], 12, 26, 9)
    if macd.empty or signal.empty:
        return "N/A"

    last_macd = macd.iloc[-1]
    last_signal = signal.iloc[-1]

    if pd.isna(last_macd) or pd.isna(last_signal):
        return "N/A"

    return "PCO" if last_macd > last_signal else "NCO"

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
            macd_state = get_macd_crossover_state(df)
            sample_df_dict[sym] = df

            if div_type:
                divergence_results[sym] = {
                    "Symbol": sym,
                    "Divergence": div_type,
                    "MACD_State": macd_state,
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
            htf_macd_state = htf_data[sym].get("MACD_State", "N/A")
            ltf_macd_state = ltf_data[sym].get("MACD_State", "N/A")

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
                    "HTF MACD": htf_macd_state,
                    "LTF MACD": ltf_macd_state,
                    "Recommendation": recommendation,
                    "Remarks": remark,
                    "Chart": make_tradingview_link(sym)
                })

    return pd.DataFrame(analytics_rows)

# ==============================================================================
# 6. HTML EMAIL DASHBOARD GENERATOR (MATCHING DASHBOARD DESIGN)
# ==============================================================================
def _rec_badge(rec: str) -> str:
    """Returns a pill-style badge (table-based, email-safe) for the recommendation."""
    styles = {
        "STRONG BUY":  ("#ecfdf5", "#059669", "#a7f3d0", "🚀"),
        "BUY":         ("#f0fdf4", "#16a34a", "#bbf7d0", "📈"),
        "STRONG SELL": ("#fef2f2", "#dc2626", "#fecaca", "🔻"),
        "SELL":        ("#fff1f2", "#e11d48", "#fecdd3", "📉"),
    }
    bg, fg, border, icon = styles.get(rec, ("#f1f5f9", "#475569", "#e2e8f0", "•"))
    return f"""<span style="display:inline-block; padding:5px 12px; border-radius:20px; background-color:{bg}; color:{fg}; border:1px solid {border}; font-size:11px; font-weight:800; letter-spacing:0.4px; white-space:nowrap;">{icon} {rec}</span>"""


def _macd_badge(state: str) -> str:
    """Returns a small colored badge for MACD crossover state (PCO / NCO)."""
    if state == "PCO":
        bg, fg, border, icon = "#ecfdf5", "#059669", "#a7f3d0", "▲"
    elif state == "NCO":
        bg, fg, border, icon = "#fef2f2", "#dc2626", "#fecaca", "▼"
    else:
        bg, fg, border, icon = "#f1f5f9", "#64748b", "#e2e8f0", "–"
    return f"""<span style="display:inline-block; padding:3px 9px; border-radius:12px; background-color:{bg}; color:{fg}; border:1px solid {border}; font-size:10px; font-weight:700; letter-spacing:0.3px; white-space:nowrap;">{icon} {state}</span>"""


def build_html_dashboard(analytics_df, date_str):
    table_rows = ""

    # Summary counts for the stat strip up top
    counts = {"STRONG BUY": 0, "BUY": 0, "STRONG SELL": 0, "SELL": 0}
    if not analytics_df.empty:
        for rec in analytics_df["Recommendation"]:
            if rec in counts:
                counts[rec] += 1

    if not analytics_df.empty:
        for idx, row in analytics_df.iterrows():
            rec = row['Recommendation']
            row_bg = "#ffffff" if idx % 2 == 0 else "#f8fafc"

            # Left accent bar color matches the recommendation sentiment
            if "BUY" in rec:
                accent = "#22c55e"
            else:
                accent = "#ef4444"

            htf_badge = _macd_badge(row.get('HTF MACD', 'N/A'))
            ltf_badge = _macd_badge(row.get('LTF MACD', 'N/A'))

            table_rows += f"""
            <tr style="background-color:{row_bg};">
                <td style="padding:0; border-left:4px solid {accent};"></td>
                <td style="padding:14px 10px; font-weight:800; color:#0f172a; font-size:13px;">{row['Stock']}</td>
                <td style="padding:14px 10px; color:#334155; font-size:11.5px; line-height:1.5;">{row['Pairing & Signals']}</td>
                <td style="padding:14px 10px; text-align:center;">{htf_badge}</td>
                <td style="padding:14px 10px; text-align:center;">{ltf_badge}</td>
                <td style="padding:14px 10px;">{_rec_badge(rec)}</td>
                <td style="padding:14px 10px; color:#64748b; font-size:11.5px; line-height:1.5;">{row['Remarks']}</td>
                <td style="padding:14px 10px; text-align:center;">
                    <a href="{row['Chart']}" style="display:inline-block; padding:6px 12px; border-radius:6px; background-color:#7c3aed; color:#ffffff; text-decoration:none; font-weight:700; font-size:11px;" target="_blank">Chart ↗</a>
                </td>
            </tr>
            <tr><td colspan="8" style="border-bottom:1px solid #eef1f5; line-height:0; font-size:0;">&nbsp;</td></tr>
            """
    else:
        table_rows = """<tr><td colspan="8" style="padding: 30px; text-align: center; color: #94a3b8; font-size: 13px;">No buy/sell recommendations generated today. Check individual timeframe sheets.</td></tr>"""

    def stat_card(label, value, bg, fg, border):
        return f"""
        <td style="padding:6px;">
            <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:{bg}; border:1px solid {border}; border-radius:10px;">
                <tr>
                    <td style="padding:12px 14px; text-align:center;">
                        <div style="font-size:20px; font-weight:800; color:{fg};">{value}</div>
                        <div style="font-size:10px; font-weight:700; color:{fg}; text-transform:uppercase; letter-spacing:0.5px; margin-top:2px;">{label}</div>
                    </td>
                </tr>
            </table>
        </td>
        """

    stats_row = (
        stat_card("Strong Buy", counts["STRONG BUY"], "#ecfdf5", "#059669", "#a7f3d0")
        + stat_card("Buy", counts["BUY"], "#f0fdf4", "#16a34a", "#bbf7d0")
        + stat_card("Strong Sell", counts["STRONG SELL"], "#fef2f2", "#dc2626", "#fecaca")
        + stat_card("Sell", counts["SELL"], "#fff1f2", "#e11d48", "#fecdd3")
    )

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #eef2f9; margin: 0; padding: 24px; color: #1e293b;">
        <div style="max-width: 1080px; margin: 0 auto; background-color: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 10px 30px rgba(30, 41, 59, 0.12); border: 1px solid #e2e8f0;">

            <!-- Dashboard Title Header (gradient banner) -->
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#1e1b4b; background-image: linear-gradient(135deg, #1e1b4b 0%, #4c1d95 45%, #7e22ce 100%);">
                <tr>
                    <td style="padding: 26px 28px;">
                        <div style="font-size: 11px; font-weight:700; letter-spacing:2px; color:#c4b5fd; text-transform:uppercase; margin-bottom:6px;">
                            ⚡ MACD MULTI-TIMEFRAME SCANNER
                        </div>
                        <div style="font-size: 22px; font-weight: 800; color: #ffffff; letter-spacing:0.3px;">
                            🎯 HTPL DASHBOARD &nbsp;<span style="color:#c4b5fd; font-weight:600;">(Buy / Sell Recommendations)</span>
                        </div>
                        <div style="font-size:12px; color:#ddd6fe; margin-top:6px;">
                            📅 {date_str} &nbsp;•&nbsp; HTF + LTF Divergence Confluence &amp; MACD Crossover State
                        </div>
                    </td>
                </tr>
            </table>

            <!-- Summary Stat Strip -->
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f8fafc; border-bottom:1px solid #e2e8f0;">
                <tr>
                    <td style="padding: 14px 20px;">
                        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                            <tr>
                                {stats_row}
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>

            <!-- Dashboard Table -->
            <div style="padding: 0; overflow-x:auto;">
                <table role="presentation" style="width: 100%; border-collapse: collapse; text-align: left; background-color: #ffffff;">
                    <thead>
                        <tr style="background-color: #eef2ff; color: #4338ca; font-size: 10.5px; text-transform: uppercase; letter-spacing:0.4px;">
                            <th style="padding: 12px 0;"></th>
                            <th style="padding: 12px 10px;">Stock</th>
                            <th style="padding: 12px 10px;">Pairing & Signals</th>
                            <th style="padding: 12px 10px; text-align:center;">HTF MACD</th>
                            <th style="padding: 12px 10px; text-align:center;">LTF MACD</th>
                            <th style="padding: 12px 10px;">Recommendation</th>
                            <th style="padding: 12px 10px;">Remarks</th>
                            <th style="padding: 12px 10px; text-align:center;">Chart</th>
                        </tr>
                    </thead>
                    <tbody>
                        {table_rows}
                    </tbody>
                </table>
            </div>

            <!-- Legend -->
            <div style="padding: 14px 20px; background-color:#f8fafc; border-top:1px solid #e2e8f0; font-size:10.5px; color:#94a3b8;">
                <strong style="color:#64748b;">Legend:</strong>&nbsp;
                PCO = MACD Line above Signal Line (Positive Cross Over) &nbsp;|&nbsp;
                NCO = MACD Line below/equal Signal Line (Negative Cross Over)
            </div>

            <!-- Footer -->
            <div style="padding: 14px 20px; background-color: #1e1b4b; text-align: center; color: #c4b5fd; font-size: 11px;">
                Generated on {date_str} &bull; MACD Divergence Scanner Engine &bull; HTPL
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
