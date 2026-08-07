import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def get_live_quote(symbol, headers):
    url = f"https://sandbox.tradier.com/v1/markets/quotes?symbols={symbol}"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json().get('quotes', {}).get('quote', {})
    return {}

def manage_order_chase(symbol="NVDA", tolerance_pct=0.0005):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    print("=" * 95)
    print(f"🔄  HARM.AI // CANCEL & REORDER ACTIVE LIMIT CHASER ENGINE (UPGRADED)")
    print("=" * 95)

    # 1. Fetch current open orders
    orders_resp = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers)
    if orders_resp.status_code != 200:
        print("[-] Failed to query order book.")
        return

    orders_data = orders_resp.json().get('orders', {})
    if not orders_data or orders_data is None:
        print("[📝] No active orders on the book to manage.")
        return

    orders = orders_data.get('order', [])
    if not isinstance(orders, list):
        orders = [orders]

    active_limit_orders = [o for o in orders if o.get('symbol') == symbol and o.get('status') == 'open' and o.get('type') == 'limit']

    if not active_limit_orders:
        print(f"[✓] No active limit orders currently pending for {symbol}.")
        return

    # 2. Get live quote to check current market boundaries
    quote = get_live_quote(symbol, headers)
    if not quote:
        print("[-] Couldn't fetch live asset quotes.")
        return

    bid = float(quote.get('bid', 0.0))
    ask = float(quote.get('ask', 0.0))
    midpoint = round((bid + ask) / 2, 2)
    print(f"[*] Live Market - Bid: ${bid:.2f} | Ask: ${ask:.2f} | Midpoint: ${midpoint:.2f}")

    for order in active_limit_orders:
        order_id = order.get('id')
        current_limit = float(order.get('price', 0.0))
        qty = int(float(order.get('quantity', 1.0)))
        side = order.get('side')

        # Check if our current limit is too far from the live midpoint
        deviation = abs(current_limit - midpoint) / midpoint
        print(f"[*] Order ID {order_id} | Side: {side} | Limit: ${current_limit:.2f} | Deviation: {deviation:.4%}")

        if deviation > tolerance_pct:
            print(f"[🚨] Deviation exceeds tolerance threshold ({tolerance_pct:.4%}). Modifying order...")
            
            # Use PUT to modify the order price directly
            modify_url = f"{base_url}/accounts/{account_id}/orders/{order_id}"
            payload = {
                'type': 'limit',
                'price': f"{midpoint:.2f}",
                'duration': 'day'
            }
            
            modify_r = requests.put(modify_url, data=payload, headers=headers)
            if modify_r.status_code == 200:
                new_order_data = modify_r.json().get('order', {})
                print(f"  [🚀] Successfully modified Order ID {order_id} to new limit price: ${midpoint:.2f}")
            else:
                print(f"  [-] Failed to modify order {order_id}: {modify_r.text}")
        else:
            print(f"  [✓] Order ID {order_id} is within tolerance limits. Leaving active.")

if __name__ == "__main__":
    manage_order_chase()
