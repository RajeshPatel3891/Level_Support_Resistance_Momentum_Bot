import os
import sys
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

def fetch_filtered_orders(statuses=None):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    params = {}
    if statuses:
        params['status'] = ",".join(statuses)

    url = f"{base_url}/accounts/{account_id}/orders"
    r = requests.get(url, headers=headers, params=params)
    
    print("=" * 95)
    print(f"📋 HARM.AI // TRADIER ORDER LOG PIPELINE (FILTERED: {statuses or 'ALL'})")
    print("=" * 95)

    if r.status_code != 200:
        print(f"[-] Failed to fetch orders: {r.text}")
        return

    orders_data = r.json().get('orders', {}) or {}
    orders_list = orders_data.get('order', []) if orders_data else []
    if not isinstance(orders_list, list):
        orders_list = [orders_list]

    if not orders_list:
        print("[📝] No matching orders found for current filter.")
        return

    print(f"{'Order ID':<12} | {'Class':<6} | {'Symbol':<22} | {'Side':<13} | {'Qty':<5} | {'Price':<8} | {'Status':<10}")
    print("-" * 95)
    
    for o in orders_list:
        if not o:
            continue
        oid = o.get('id')
        oclass = o.get('class', '').upper()
        symbol = o.get('option_symbol') or o.get('symbol', '')
        side = o.get('side', '').upper()
        qty = float(o.get('quantity', 0))
        
        # Safe evaluation of nullable float types (e.g. Market Orders)
        raw_price = o.get('price')
        if raw_price is not None:
            try:
                price = f"${float(raw_price):,.2f}"
            except ValueError:
                price = "MKT"
        else:
            price = "MKT"
            
        status = o.get('status', '').upper()
        
        print(f"{oid:<12} | {oclass:<6} | {symbol:<22} | {side:<13} | {qty:<5.1f} | {price:<8} | {status:<10}")
    
    print("-" * 95)
    print(f"[⚙️] Rendered {len(orders_list)} matching entries.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="View Tradier orders filtered by status.")
    parser.add_argument("--status", type=str, help="Comma-separated statuses to filter by (e.g. open,filled,rejected)")
    args = parser.parse_args()

    filter_list = [s.strip().lower() for s in args.status.split(",")] if args.status else None
    fetch_filtered_orders(filter_list)
