from datetime import date, timedelta
import json
import os
import re
import pandas as pd
import requests


def nse_session():
  s = requests.Session()
  s.headers.update({
      "User-Agent": "Mozilla/5.0",
      "Accept": "application/json",
      "Referer": "https://www.nseindia.com/",
  })
  return s


def extract_order_value(text):
  if not text:
    return None
  m = re.search(r"(₹|Rs\.?)\s?([\d,]+)\s?crore", text, re.I)
  return float(m.group(2).replace(",", "")) if m else None


def extract_completion_time(text):
  if not text:
    return "Not Specified"
  m = re.search(
      r"(within|over|in)\s(\d+)\s(year|years|month|months)", text, re.I
  )
  return f"{m.group(2)} {m.group(3)}" if m else "Not Specified"


def fetch_nse_orders_range(start_date, end_date):
  s = nse_session()
  try:
    s.get("https://www.nseindia.com", timeout=5)
    url = "https://www.nseindia.com/api/corporate-announcements"
    params = {
        "index": "equities",
        "from_date": start_date.strftime("%d-%m-%Y"),
        "to_date": end_date.strftime("%d-%m-%Y"),
    }
    r = s.get(url, params=params, timeout=10)
    data = r.json()
    if not data:
      return pd.DataFrame()
    df = pd.DataFrame(data)
    df["Date"] = pd.to_datetime(df["sort_date"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    return df
  except Exception as e:
    print(f"Error fetching announcements: {e}")
    return pd.DataFrame()


def fetch_nse_equity(symbol):
  try:
    s = nse_session()
    s.get("https://www.nseindia.com", timeout=5)
    url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
    r = s.get(url, timeout=5)
    data = r.json()
    return {
        "marketCap": data["metadata"].get("marketCap"),
        "sector": data["metadata"].get("industry", "NA"),
    }
  except Exception as e:
    print(f"Error fetching equity info for {symbol}: {e}")
    return None


def run_data_pipeline():
  start_date = date.today() - timedelta(days=7)
  end_date = date.today()

  print(f"Fetching data from {start_date} to {end_date}...")
  orders = fetch_nse_orders_range(start_date, end_date)

  if orders.empty:
    print("No order data retrieved.")
    return

  orders = orders[
      orders["attchmntText"].str.contains(
          "order|contract|award|project|agreement|loa", case=False, na=False
      )
  ]

  announcements = []
  results = []

  for _, r in orders.iterrows():
    sym = r.get("symbol", "")
    sm_name = r.get("sm_name", "")
    desc = r.get("desc", "")
    order_date = r.get("Date", "")
    attachment = r.get("attchmntFile", "#")
    attch_text = r.get("attchmntText", "")

    announcements.append({
        "symbol": sym,
        "sm_name": sm_name,
        "desc": desc,
        "Date": order_date,
        "attchmntFile": attachment,
        "screener_url": (
            f"https://www.screener.in/company/{sym}/consolidated/"
        ),
    })

    order_val = extract_order_value(attch_text)
    eq = fetch_nse_equity(sym)

    if eq and eq.get("marketCap") and order_val:
      market_cap_cr = eq["marketCap"] / 1e7
      impact = min((order_val / market_cap_cr) * 5, 100)

      results.append({
          "symbol": sym,
          "company": sm_name,
          "desc": desc,
          "order_val_cr": round(order_val, 1),
          "market_cap_cr": round(market_cap_cr, 0),
          "order_pct_mcap": round((order_val / market_cap_cr) * 100, 2),
          "completion_time": extract_completion_time(attch_text),
          "sector": eq["sector"],
          "impact_score": round(impact, 1),
          "order_date": order_date,
          "screener_url": (
              f"https://www.screener.in/company/{sym}/consolidated/"
          ),
          "pdf_url": attachment,
      })

  final_output = {"announcements": announcements, "rankings": results}

  # Dynamically saves directly inside the orderbook/ directory
  script_dir = os.path.dirname(os.path.abspath(__file__))
  output_file_path = os.path.join(script_dir, "nse_orders_data.json")

  with open(output_file_path, "w", encoding="utf-8") as f:
    json.dump(final_output, f, indent=4)

  print(f"Data saved successfully to {output_file_path}")


if __name__ == "__main__":
  run_data_pipeline()
