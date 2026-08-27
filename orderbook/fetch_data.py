from datetime import date, timedelta
import json
import os
import re
import pandas as pd
import requests

# ... Keep all helper functions (nse_session, extract_order_value, etc.) unchanged ...


def run_data_pipeline():
  start_date = date.today() - timedelta(days=7)  #[cite: 2]
  end_date = date.today()  #[cite: 2]

  print(f"Fetching data from {start_date} to {end_date}...")  #[cite: 2]
  orders = fetch_nse_orders_range(start_date, end_date)  #[cite: 2]

  if orders.empty:  #[cite: 2]
    print("No order data retrieved.")  #[cite: 2]
    return  #[cite: 2]

  # Filter announcements for order keywords
  orders = orders[  #[cite: 2]
      orders["attchmntText"].str.contains(  #[cite: 2]
          "order|contract|award|project|agreement|loa",
          case=False,
          na=False,  #[cite: 2]
      )  #[cite: 2]
  ]  #[cite: 2]

  announcements = []  #[cite: 2]
  results = []  #[cite: 2]

  for _, r in orders.iterrows():  #[cite: 2]
    sym = r.get("symbol", "")  #[cite: 2]
    sm_name = r.get("sm_name", "")  #[cite: 2]
    desc = r.get("desc", "")  #[cite: 2]
    order_date = r.get("Date", "")  #[cite: 2]
    attachment = r.get("attchmntFile", "#")  #[cite: 2]
    attch_text = r.get("attchmntText", "")  #[cite: 2]

    announcements.append({  #[cite: 2]
        "symbol": sym,  #[cite: 2]
        "sm_name": sm_name,  #[cite: 2]
        "desc": desc,  #[cite: 2]
        "Date": order_date,  #[cite: 2]
        "attchmntFile": attachment,  #[cite: 2]
        "screener_url": (
            f"https://www.screener.in/company/{sym}/consolidated/"
        ),  #[cite: 2]
    })

    order_val = extract_order_value(attch_text)  #[cite: 2]
    eq = fetch_nse_equity(sym)  #[cite: 2]

    if eq and eq.get("marketCap") and order_val:  #[cite: 2]
      market_cap_cr = eq["marketCap"] / 1e7  #[cite: 2]
      impact = min((order_val / market_cap_cr) * 5, 100)  #[cite: 2]

      results.append({  #[cite: 2]
          "symbol": sym,  #[cite: 2]
          "company": sm_name,  #[cite: 2]
          "order_val_cr": round(order_val, 1),  #[cite: 2]
          "market_cap_cr": round(market_cap_cr, 0),  #[cite: 2]
          "order_pct_mcap": round((order_val / market_cap_cr) * 100, 2),  #[cite: 2]
          "completion_time": extract_completion_time(attch_text),  #[cite: 2]
          "sector": eq["sector"],  #[cite: 2]
          "impact_score": round(impact, 1),  #[cite: 2]
          "order_date": order_date,  #[cite: 2]
          "screener_url": (
              f"https://www.screener.in/company/{sym}/consolidated/"
          ),  #[cite: 2]
          "pdf_url": attachment,  #[cite: 2]
      })

  final_output = {
      "announcements": announcements,
      "rankings": results,
  }  #[cite: 2]

  # =========================================================
  # UPDATED PATH LOGIC: Targets orderbook/ directly
  # =========================================================
  script_dir = os.path.dirname(os.path.abspath(__file__))
  output_file_path = os.path.join(script_dir, "nse_orders_data.json")

  with open(output_file_path, "w", encoding="utf-8") as f:
    json.dump(final_output, f, indent=4)

  print(f"Data saved successfully to {output_file_path}")


if __name__ == "__main__":
  run_data_pipeline()  #[cite: 2]
