import streamlit as st
from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import talib as ta
import numpy as np
from datetime import datetime, time
import datetime as dt
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from io import BytesIO
from fpdf import FPDF
#import pyswisseph as swe
import swisseph as swe
import hashlib
import base64

def set_bg_image(image_path: str):
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{encoded}");
            background-size: cover;
            background-position: center;
            background-repeat: no-repeat;
            background-attachment: fixed;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )



# ---------------- PASSWORD HASH ----------------
def hash_pwd(pwd):
    return hashlib.sha256(pwd.encode()).hexdigest()

# ---------------- USERS ----------------
USERS = st.secrets["users"]

# 🔐 Users allowed to select ANY future date
FUTURE_ALLOWED_USERS = {
    "admin",
    "gaurav",
    "premium",
    "EGAVSIV",
    "DIPTI"
}

# ---------------- SESSION INIT ----------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if "username" not in st.session_state:
    st.session_state.username = None

if not st.session_state.authenticated:
    st.title("🔐 Login Required")

    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        if u in USERS and hash_pwd(p) == USERS[u]:
            st.session_state.authenticated = True
            st.session_state.username = u   # ✅ STORE USERNAME
            st.rerun()
        else:
            st.error("Invalid credentials")

    st.stop()




# -------------------------------------------------
# GLOBAL PAGE CONFIG
# -------------------------------------------------
st.set_page_config(page_title="FNO Reversal Levels & Reversal Time_By_Gaurav_Singh_Yadav", layout="wide",page_icon="🔁")
col_logo, col_ticker = st.columns([0.22, 0.78])

with col_logo:
    st.image("Assets/sgy1.png", width=220)    

set_bg_image("Assets/BG11.png")


# -------------------------------------------------
# BACKGROUND IMAGE
# -------------------------------------------------
def set_background(image_path: str):
    try:
        with open(image_path, "rb") as f:
            img_data = f.read()
        b64 = base64.b64encode(img_data).decode()
    except Exception:
        return

    css = f"""
    <style>
    [data-testid="stAppViewContainer"] > .main {{
        background-image: url("data:image/png;base64,{b64}");
        background-size: cover;
        background-position: center;
        background-attachment: fixed;
    }}
    .css-18e3th9.ehxs19n2 {{
        background-color: rgba(0,0,0,0) !important;
    }}
    body {{background-color: #111;}}
    .stApp {{background-color: #000;}}
    .big {{
        font-size: 28px;
        font-weight: bold;
        color: #00ff99;
    }}
    .greenbox {{
        background: #003300;
        padding: 15px;
        color: #00ff99;
        border-radius: 10px;
    }}
    .yellowbox {{
        background: #332b00;
        padding: 15px;
        color: #ffee55;
        border-radius: 10px;
    }}
    .redbox {{
        background: #330000;
        padding: 15px;
        color: #ff5555;
        border-radius: 10px;
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

set_background("SMB2.jpg")

st.title("FNO Reversal Levels & Reversal Time_By_Gaurav_S_Yadav")

# -------------------------------------------------
# TVDATAFEED INIT
# -------------------------------------------------
tv = TvDatafeed()

# -------------------------------------------------
# SYMBOL UNIVERSE (same as before)
# -------------------------------------------------
SYMBOLS =  ['NIFTY','BANKNIFTY','CNXFINANCE','CNXMIDCAP','NIFTYJR','WAAREEENER','PREMIERENE','SWIGGY',"TMPV",
    'PIDILITIND','PERSISTENT','PETRONET','LTM','INDIANB','INDHOTEL','COCHINSHIP','HAVELLS','BRITANNIA','BSE',
    'CAMS','CANBK','CDSL','CGPOWER','CHOLAFIN','CIPLA','COALINDIA','COFORGE','COLPAL','CONCOR','CROMPTON',
    'CUMMINSIND','ADANIPOWER','DABUR','DALBHARAT','DELHIVERY','DIVISLAB','DIXON','DLF','DMART','DRREDDY',
    'EICHERMOT','ETERNAL','EXIDEIND','FEDERALBNK','FORTIS','GAIL','GLENMARK','GMRAIRPORT','GODREJCP','GODREJPROP',
    'GRASIM','HAL','HDFCAMC','HDFCBANK','HDFCLIFE','HEROMOTOCO','HINDALCO','HINDPETRO','HINDUNILVR','HINDZINC',
    'FORCEMOT','ICICIBANK','ICICIGI','ICICIPRULI','IDEA','IDFCFIRSTB','IEX','GVT&D','GODFRYPHLP','INDIGO','INDUSINDBK',
    'INDUSTOWER','INFY','INOXWIND','IOC','HYUNDAI','IREDA','IRFC','ITC','JINDALSTEL','JIOFIN','JSWENERGY',
    'JSWSTEEL','JUBLFOOD','KALYANKJIL','KAYNES','KEI','KFINTECH','KOTAKBANK','KPITTECH','LAURUSLABS',
    'LICHSGFIN','LICI','LODHA','LT','LTF','LUPIN','M&M','MANAPPURAM','MANKIND','MARICO','MARUTI','MAXHEALTH',
    'MAZDOCK','MCX','MFSL','MOTHERSON','MPHASIS','MUTHOOTFIN','NATIONALUM','NAUKRI','NBCC','MOTILALOFS','NESTLEIND',
    'NMDC','NTPC','NUVAMA','NYKAA','OBEROIRLTY','OFSS','OIL','ONGC','PAGEIND','PATANJALI','PAYTM',
    'PFC','PGEL','PHOENIXLTD','PIIND','PNB','PNBHOUSING','POLICYBZR','POLYCAB','NHPC','HCLTECH','POWERGRID',
    'NAM_INDIA','PRESTIGE','RBLBANK','RECLTD','RELIANCE','RVNL','SAIL','POWERINDIA','SBICARD','SBILIFE',
    'SBIN','SHREECEM','SHRIRAMFIN','SIEMENS','SOLARINDS','SONACOMS','SRF','SUNPHARMA','SUPREMEIND','SUZLON',
    'RADICO','TATACONSUM','TATAELXSI','TATAPOWER','TATASTEEL','VMM','TCS','TECHM','TIINDIA',
    'TITAN','TORNTPHARM','TRENT','TVSMOTOR','ULTRACEMCO','UNIONBANK','UNITDSPR',
    'UNOMINDA','UPL','VBL','VEDL','VOLTAS','WIPRO','YESBANK','ZYDUSLIFE','BANKNIFTY','CNXFINANCE','CNXMIDCAP',
    'NIFTY','NIFTYJR','360ONE','ABB','ABCAPITAL','ADANIENSOL','ADANIENT','ADANIGREEN','ADANIPORTS','ALKEM',
    'AMBER','AMBUJACEM','ANGELONE','APLAPOLLO','APOLLOHOSP','ASHOKLEY','ASIANPAINT','ASTRAL','AUBANK',
    'AUROPHARMA','AXISBANK','BAJAJ_AUTO','BAJAJFINSV','BAJFINANCE','BANDHANBNK','BANKBARODA','BANKINDIA',
    'BDL','BEL','BHARATFORG','BHARTIARTL','BHEL','BIOCON','BLUESTARCO','BOSCHLTD','BPCL','BAJAJHLDNG']

# -------------------------------------------------
# COMMON PRICE FUNCTIONS
# -------------------------------------------------
def get_weekly_close(symbol: str, exchange: str = "NSE"):
    try:
        df = tv.get_hist(symbol=symbol, exchange=exchange,
                         interval=Interval.in_weekly, n_bars=2)
    except Exception:
        return None, None
    if df is None or df.empty or "close" not in df.columns:
        return None, None
    df = df.dropna(subset=["close"])
    if len(df) < 2:
        return None, None
    last = float(df["close"].iloc[-1])
    prev = float(df["close"].iloc[-2])
    now = datetime.now()
    if (now.weekday() == 4 and now.time() >= time(15, 30)) or now.weekday() in (5, 6):
        return last, df.index[-1]
    else:
        return prev, df.index[-2]

def fetch_daily(symbol: str, exchange: str = "NSE", bars: int = 60):
    try:
        df = tv.get_hist(symbol=symbol, exchange=exchange,
                         interval=Interval.in_daily, n_bars=bars)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    if not {"open","high","low","close"}.issubset(df.columns):
        return None
    return df.dropna(subset=["open","high","low","close"])

def get_atr_with_talib(daily_df, period=10):
    atr_arr = ta.ATR(
        daily_df["high"], daily_df["low"], daily_df["close"],
        timeperiod=period
    )
    val = atr_arr.iloc[-1]
    return None if np.isnan(val) else float(val)

def price_cycles(close_price: float, steps):
    res, sup = [], []
    up = down = close_price
    for s in steps:
        up += s
        down -= s
        res.append(up)
        sup.append(down)
    return res, sup

# =================================================
#      SECTION 1 — ASTRO REVERSAL TIME SCANNER
# =================================================
# Swisseph config
swe.set_sid_mode(swe.SIDM_LAHIRI)
LAT = 19.07598
LON = 72.87766
FLAGS = swe.FLG_SWIEPH | swe.FLG_SIDEREAL

START = (9, 15)
END   = (15, 30)

NAKSHATRAS = [
    "Ashwini","Bharani","Krittika","Rohini","Mrigashira",
    "Ardra","Punarvasu","Pushya","Ashlesha","Magha",
    "Purva Phalguni","Uttara Phalguni","Hasta","Chitra",
    "Swati","Vishakha","Anuradha","Jyeshtha","Mula",
    "Purva Ashadha","Uttara Ashadha","Shravana","Dhanishtha",
    "Shatabhisha","Purva Bhadrapada","Uttara Bhadrapada","Revati"
]

ZODIAC_SIGNS = [
    "Aries","Taurus","Gemini","Cancer","Leo","Virgo",
    "Libra","Scorpio","Sagittarius","Capricorn","Aquarius","Pisces"
]

NAK_BIAS = {
    "Rohini":"Bullish / accumulation",
    "Mrigashira":"Trend friendly",
    "Punarvasu":"Recovery bounce",
    "Pushya":"Institutional strength",
    "Hasta":"Scalping friendly",
    "Chitra":"Breakout bias",
    "Swati":"Independent volatility",
    "Anuradha":"Continuation",
    "Uttara Ashadha":"Follow-through trend",
    "Shravana":"News trend",
    "Dhanishtha":"Momentum",
    "Revati":"Calm / mild trend",
    "Bharani":"Profit booking",
    "Ardra":"Panic / crash risk",
    "Ashlesha":"Fake breakout",
    "Magha":"Gap and dump",
    "Mula":"Sharp reversal",
    "Purva Ashadha":"Aggressive",
    "Jyeshtha":"Sharp reversal",
    "Purva Bhadrapada":"Extreme swings",
    "Krittika":"High volatility",
    "Purva Phalguni":"Overtrading",
    "Uttara Phalguni":"Trend after confusion",
    "Vishakha":"Two leg move",
    "Shatabhisha":"Algo / fake breaks",
    "Uttara Bhadrapada":"Late reversal",
}

PLANETS = {
    "Mars": swe.MARS,
    "Saturn": swe.SATURN,
    "Rahu": swe.MEAN_NODE,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS
}

ASPECTS = [0, 45, 60, 90, 120, 180]
ORB_DEG = 1.0

NAK_SIZE = 360/27
PADA_SIZE = NAK_SIZE/4

def jd_from_ist(d):
    d_utc = d - dt.timedelta(hours=5, minutes=30)
    return swe.julday(d_utc.year, d_utc.month, d_utc.day,
                      d_utc.hour + d_utc.minute/60)

def lon(jd, planet):
    pos, _ = swe.calc_ut(jd, planet, FLAGS)
    return pos[0] % 360

def get_nak_pada(l):
    i = int(l // NAK_SIZE)
    pada = int(((l - i*NAK_SIZE) // PADA_SIZE) + 1)
    return NAKSHATRAS[i], pada

def angle(a, b):
    d = abs(a - b) % 360
    return 360 - d if d > 180 else d

def get_ascendant(jd):
    ascmc, cusp = swe.houses_ex(jd, LAT, LON, b'P', FLAGS)
    asc = ascmc[0] % 360
    sign_index = int(asc // 30)
    return ZODIAC_SIGNS[sign_index], asc

def scan_astro(date, step=5):
    rows = []
    last_nak, last_pada, last_asc = None, None, None

    t = dt.datetime(date.year, date.month, date.day, START[0], START[1])
    end = dt.datetime(date.year, date.month, date.day, END[0], END[1])

    while t <= end:
        jd = jd_from_ist(t)

        m = lon(jd, swe.MOON)
        nak, pada = get_nak_pada(m)
        asc, _ = get_ascendant(jd)

        if last_asc and asc != last_asc:
            rows.append([t, "Ascendant Change", f"{last_asc} -> {asc}"])

        if last_nak and nak != last_nak:
            rows.append([t, "Nakshatra Change", f"{last_nak} -> {nak}"])

        if last_pada and pada != last_pada:
            rows.append([t, "Pada Change", f"{last_pada} -> {pada}"])

        for pname, pid in PLANETS.items():
            p = lon(jd, pid)
            for asp in ASPECTS:
                if angle(m, (p - asp) % 360) <= ORB_DEG:
                    rows.append([t, f"Moon-{pname}", f"{asp}°"])

        last_asc, last_nak, last_pada = asc, nak, pada
        t += dt.timedelta(minutes=step)

    df = pd.DataFrame(rows, columns=["Time", "Event", "Detail"])
    return nak, NAK_BIAS.get(nak, "Neutral"), df

# ------------- ASTRO UI ------------- #
st.header("🔮 FNO Reversal Time (Astro)")

c1, c2, c3 = st.columns(3)
with c1:
    today = dt.date.today()
tomorrow = today + dt.timedelta(days=1)

# Decide max selectable date
if st.session_state.username in FUTURE_ALLOWED_USERS:
    max_date = None              # Unlimited future dates
else:
    max_date = today + dt.timedelta(days=2)   # Today + 2         # Only Day +1 allowed

picked = st.date_input(
    "Select Date",
    value=today,
    min_value=None,              # Past dates allowed
    max_value=max_date           # Conditional future limit
)

# 🔔 INFO MESSAGE FOR LIMITED USERS
if st.session_state.username not in FUTURE_ALLOWED_USERS:
    st.info("ℹ️ Future date selection is limited to Tomorrow+1 only for your login.")

with c2:
    if st.button("Today"):
        picked = dt.date.today()
with c3:
    if st.button("Now (Live)"):
        picked = dt.datetime.now().date()

nak, bias, df_astro = scan_astro(picked)

if "bull" in bias.lower() or "strength" in bias.lower():
    box = "greenbox"
elif "reversal" in bias.lower() or "risk" in bias.lower():
    box = "redbox"
else:
    box = "yellowbox"

st.markdown(
    f"<div class='{box}'><span class='big'>Moon Nakshatra: {nak}</span><br>"
    f"Bias: {bias}</div>",
    unsafe_allow_html=True
)

st.markdown("### 🔁 Intraday Astro Events")

if df_astro.empty:
    st.warning("No events detected.")
else:
    df_astro["Time"] = df_astro["Time"].dt.strftime("%H:%M")
    st.dataframe(df_astro, use_container_width=True)

st.markdown("---")

# =================================================
# SECTION 2 — PRICE CYCLE SUPPORT/RESISTANCE
# =================================================
st.header("🎯 Price Cycle Support & Resistance Levels")

mode = st.radio("Mode:", ["Single Symbol", "Scan Universe (by ATR%)"])

# -------------------- SINGLE SYMBOL --------------------
if mode == "Single Symbol":

    symbol = st.selectbox("Select Symbol", SYMBOLS)

    weekly_close, wdate = get_weekly_close(symbol)
    if weekly_close is None:
        st.error("⛔ Could not fetch weekly data.")
        st.stop()

    df_daily = fetch_daily(symbol)
    if df_daily is None or df_daily.empty:
        st.error("⛔ Could not fetch daily data.")
        st.stop()

    last_close = float(df_daily["close"].iloc[-1])
    last_ts = df_daily.index[-1]
    atr = get_atr_with_talib(df_daily)

    # Header info
    st.markdown(
        f"### <span style='color:blue; font-size:26px; font-weight:bold;'>{symbol}</span>",
        unsafe_allow_html=True
    )
    st.markdown(
        f"<div style='font-size:18px;'>Weekly Close: <b>{weekly_close:.2f}</b> "
        f"&nbsp;&nbsp; (Bar Date: {wdate.date()})</div>",
        unsafe_allow_html=True
    )
    st.markdown(
        f"<div style='font-size:18px;'>Last Daily Candle: <b>{last_ts}</b> "
        f"&nbsp;&nbsp; Last Close: <b>{last_close:.2f}</b></div>",
        unsafe_allow_html=True
    )
    if atr:
        atrp = (atr / last_close) * 100
        st.markdown(
            f"<div style='font-size:18px;'>ATR(10): <b>{atr:.2f}</b> "
            f"&nbsp;&nbsp; ATR%: <b>{atrp:.2f}%</b></div>",
            unsafe_allow_html=True
        )

    st.markdown("---")

    # Presets including Micro
    presets = {
        "Default 30-60-90-120-150": [30, 60, 90, 120, 150],
        "Short 3-6-9-12-15": [3, 6, 9, 12, 15],
        "Micro .3-.6-.9-1.2-1.5": [0.3, 0.6, 0.9, 1.2, 1.5],
        "Long 300-600-900-1200-1500": [300, 600, 900, 1200, 1500],
        "Custom": None
    }

    choice = st.selectbox("Cycle Step Preset", list(presets.keys()))

    if choice == "Custom":
        raw = st.text_input("Enter comma-separated steps", "30,60,90")
        try:
            steps = [float(x.strip()) for x in raw.split(",") if x.strip()]
        except:
            st.error("Invalid custom range")
            st.stop()
    else:
        steps = presets[choice]

    # Price cycles from weekly close
    R_raw, S_raw = price_cycles(weekly_close, steps)
    R = R_raw[:5]
    S = S_raw[:5]

    # Dynamic reclassification: R below last_close becomes S
    new_R, new_S = [], []

    for val in R:
        if val > last_close:
            new_R.append(val)
        else:
            new_S.append(val)

    for val in S:
        new_S.append(val)

    # Ensure exactly 5R & 5S (Option A)
    while len(new_R) < 5:
        new_R.append(None)
    new_R = new_R[:5]

    while len(new_S) < 5:
        new_S.append(None)
    new_S = new_S[:5]

    # ----------- DISPLAY (Styled Text) ----------- #
    st.markdown("## 🎯 Support & Resistance Levels")

    st.markdown(
        "<div style='font-size:22px; color:#ff9933; font-weight:bold;'>"
        "🔶 Resistance Levels</div>",
        unsafe_allow_html=True
    )

    for i, val in enumerate(new_R, 1):
        txt = f"R{i}: {val:.2f}" if val else f"R{i}: ---"
        st.markdown(
            f"<div style='font-size:20px; color:#ffb366;'>{txt}</div>",
            unsafe_allow_html=True
        )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:22px; background:#214275; padding:6px; "
        f"width:240px; border-radius:6px;'><b>Today Price: {last_close:.2f}</b></div>",
        unsafe_allow_html=True
    )
    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(
        "<div style='font-size:22px; color:#33cc33; font-weight:bold;'>"
        "🟢 Support Levels</div>",
        unsafe_allow_html=True
    )

    for i, val in enumerate(new_S, 1):
        txt = f"S{i}: {val:.2f}" if val else f"S{i}: ---"
        st.markdown(
            f"<div style='font-size:20px; color:#99ff99;'>{txt}</div>",
            unsafe_allow_html=True
        )

    # Export data
    df_export = pd.DataFrame({
        "Level": [f"R{i}" for i in range(1,6)] + ["Today Price"] + [f"S{i}" for i in range(1,6)],
        "Price": new_R + [last_close] + new_S
    })

    csv_data = df_export.to_csv(index=False)
    st.download_button(
        "📥 Download SR Levels CSV",
        data=csv_data,
        file_name=f"{symbol}_SR_levels.csv",
        mime="text/csv"
    )

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"{symbol} - Support & Resistance Levels", ln=True, align="C")

    for lvl, val in zip(df_export["Level"], df_export["Price"]):
        pdf.cell(50, 10, lvl, 1, 0)
        pdf.cell(40, 10, f"{val:.2f}", 1, 1)

    pdf_bytes = pdf.output(dest="S").encode("latin-1")
    st.download_button(
        "📥 Download SR Levels PDF",
        data=pdf_bytes,
        file_name=f"{symbol}_SR_levels.pdf",
        mime="application/pdf"
    )

# -------------------- ATR% SCAN --------------------
else:
    st.write("## 🔍 ATR% Scan — High Volatility Stocks")

    period = st.number_input("ATR lookback (days)", min_value=5, max_value=60, value=10, step=1)
    top_n = st.number_input("Top N volatile stocks", min_value=5, max_value=len(SYMBOLS),
                            value=20, step=5)

    results = []
    for s in SYMBOLS:
        df = fetch_daily(s)
        if df is None:
            continue
        try:
            lc = float(df["close"].iloc[-1])
            atr = get_atr_with_talib(df, period)
            if atr:
                results.append((s, lc, atr, (atr/lc)*100))
        except:
            pass

    if results:
        df_scan = pd.DataFrame(results, columns=["Symbol","Last Close","ATR","ATR%"])
        df_scan = df_scan.sort_values("ATR%", ascending=False).head(top_n)
        st.dataframe(df_scan, use_container_width=True)

        st.download_button(
            "Download ATR Scan CSV",
            df_scan.to_csv(index=False),
            "ATR_scan.csv",
            "text/csv"
        )
    else:
        st.write("No data available.")    


st.markdown("""
---
**Designed by:-**  
*Gaurav Singh Yadav*  
🩷💛🩵💙🩶💜🤍🤎💖  Built With Love 🫶  
Energy | Commodity | Quant Intelligence 📶  
📱 +91-8003994518 〽️  
📧 yadav.gauravsingh@gmail.com ™️
""")
