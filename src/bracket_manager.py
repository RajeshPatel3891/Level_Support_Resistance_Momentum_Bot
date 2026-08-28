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

def manage_position_brackets(symbol="NVDA", tp_pct=0.01, sl_pct=0.005):
    """
    Manages active position safety loops.
    tp_pct: 1% Take Profit target above cost basis
    sl_pct: 0.5% Stop Loss target below cost basis
    """
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    print("=" * 95)
    print(f"🛡️  HARM.AI // DYNAMIC POSITION SAFETY BRACKET MANAGER")
    print("=" * 95)

    # 1. Fetch current open positions
    pos_resp = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers)
    if pos_resp.status_code != 200:
        print("[-] Failed to query active positions.")
        return

    pos_data = pos_resp.json().get('positions', {}) or {}
    positions = pos_data.get('position', []) if pos_data else []
    if not isinstance(positions, list):
        positions = [positions]

    active_pos = next((p for p in positions if p.get('symbol') == symbol), None)

    if not active_pos:
        print(f"[✓] No active long exposure found for {symbol}. No brackets to manage.")
        return

    qty = int(float(active_pos.get('quantity', 0.0)))
    cost_basis = float(active_pos.get('cost_basis', 0.0))
    print(f"[*] Long Position Active: {qty} {symbol} @ Cost Basis of ${cost_basis:.2f}")

    # 2. Calculate thresholds
    tp_price = round(cost_basis * (1 + tp_pct), 2)
    sl_price = round(cost_basis * (1 - sl_pct), 2)
    print(f"[*] Upper Target (Take Profit): ${tp_price:.2f} (+{tp_pct*100:.2f}%)")
    print(f"[*] Lower Target (Stop Loss):   ${sl_price:.2f} (-{sl_pct*100:.2f}%)")

    # 3. Check for existing open orders
    orders_resp = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers)
    orders_data = orders_resp.json().get('orders', {}) or {}
    orders = orders_data.get('order', []) if orders_data else []
    if not isinstance(orders, list):
        orders = [orders]

    active_exit_order = next((o for o in orders if o.get('symbol') == symbol and o.get('status') == 'open' and o.get('side') == 'sell'), None)

    # 4. Get Live Market Price
    quote = get_live_quote(symbol, headers)
    if not quote:
        print("[-] Couldn't fetch live quotes.")
        return

    last_price = float(quote.get('last', 0.0))
    print(f"[*] Current Live Market Price: ${last_price:.2f}")

    # 5. Evaluate Bracket Execution
    if last_price >= tp_price:
        print("[🎯] TAKE PROFIT TRIGGERED! Asset crossed upper boundary.")
        execute_exit(base_url, account_id, symbol, qty, "Take Profit Exit", headers, active_exit_order)
    elif last_price <= sl_price:
        print("[🚨] STOP LOSS TRIGGERED! Asset crossed lower boundary.")
        execute_exit(base_url, account_id, symbol, qty, "Stop Loss Exit", headers, active_exit_order)
    else:
        print("[✓] Position is healthy. Trading inside safe boundaries.")

def execute_exit(base_url, account_id, symbol, qty, reason, headers, active_exit_order):
    """Executes a fast market exit or updates an existing order to fill immediately."""
    if active_exit_order:
        order_id = active_exit_order.get('id')
        print(f"[*] Modifying existing exit Order ID {order_id} to market order via PUT...")
        modify_url = f"{base_url}/accounts/{account_id}/orders/{order_id}"
        payload = {
            'type': 'market',
            'duration': 'day'
        }
        r = requests.put(modify_url, data=payload, headers=headers)
        if r.status_code == 200:
            print(f"[✓] {reason} executed cleanly via modified Order ID {order_id}.")
        else:
            print(f"[-] Modification failed: {r.text}")
    else:
        print(f"[*] Dispatching immediate market sell order for {qty} shares...")
        payload = {
            'class': 'equity',
            'symbol': symbol,
            'side': 'sell',
            'quantity': str(qty),
            'type': 'market',
            'duration': 'day'
        }
        # HARD SECURITY FLOOR
        import os
        env_chk = os.getenv("EXECUTION_ENV", "SANDBOX").upper()
        if env_chk == "SANDBOX" and str(account_id) == "6YB87601":
            print("[🚨 SECURITY BLOCK] Bracket Manager blocked order dispatch to Live Prod Account ID (6YB87601) under SANDBOX mode.")
            return None
        r = requests.post(f"{base_url}/accounts/{account_id}/orders", data=payload, headers=headers)
        if r.status_code == 200:
            print(f"[✓] {reason} executed cleanly via new Market Order ID: {r.json().get('order', {}).get('id')}")
        else:
            print(f"[-] Order placement failed: {r.text}")

if __name__ == "__main__":
    manage_position_brackets()
