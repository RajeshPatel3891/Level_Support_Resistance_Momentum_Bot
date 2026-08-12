import os
import requests
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN')
acc_id = os.getenv('TRADIER_ACCOUNT_ID')
base_url = "https://sandbox.tradier.com/v1"
headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

print("[*] Checking open Tradier sandbox orders...")
orders_res = requests.get(f"{base_url}/accounts/{acc_id}/orders", headers=headers)
if orders_res.status_code == 200:
    orders = orders_res.json().get('orders', {}).get('order', [])
    if isinstance(orders, dict):
        orders = [orders]
    for o in orders:
        if o.get('status') in ['open', 'pending']:
            oid = o.get('id')
            print(f" -> Canceling open order #{oid}...")
            requests.delete(f"{base_url}/accounts/{acc_id}/orders/{oid}", headers=headers)

print("[*] Checking open Tradier sandbox positions...")
pos_res = requests.get(f"{base_url}/accounts/{acc_id}/positions", headers=headers)
if pos_res.status_code == 200:
    positions = pos_res.json().get('positions', {}).get('position', [])
    if isinstance(positions, dict):
        positions = [positions]
    for p in positions:
        sym = p.get('symbol')
        qty = p.get('quantity')
        print(f" -> Found position {sym} (Qty: {qty}). Closing position...")
        # Submit closing market order
        side = "sell_to_close" if float(qty) > 0 else "buy_to_close"
        payload = {"class": "option", "symbol": sym[:4].strip("0123456789 "), "option_symbol": sym, "side": side, "quantity": str(abs(int(float(qty)))), "type": "market", "duration": "day"}
        requests.post(f"{base_url}/accounts/{acc_id}/orders", data=payload, headers=headers)

print("[✓] Tradier sandbox cleanup complete. Check balances again in a moment.")
