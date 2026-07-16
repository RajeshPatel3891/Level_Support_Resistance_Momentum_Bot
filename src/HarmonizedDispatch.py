import os
import requests
from dotenv import load_dotenv

load_dotenv()

def get_atm_option_symbol(symbol, direction):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    resp = requests.get(f"{base_url}/markets/options/chains?symbol={symbol}&expiration=2026-07-17", headers=headers)
    data = resp.json()
    options_data = data.get('options') if data else None
    options_dict = options_data or {}
    options = options_dict.get('option', [])
    return options[0]['symbol'] if options else None

def get_position_pnl(symbol, threshold=0.0):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    resp = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers)
    pos_data = resp.json().get('positions', {}).get('position', [])
    if isinstance(pos_data, dict): pos_data = [pos_data]
    
    target = next((p for p in pos_data if p['symbol'] == symbol), None)
    if not target: return False
    
    # Calculate current value
    quote_resp = requests.get(f"{base_url}/markets/quotes?symbols={symbol}", headers=headers)
    quote = quote_resp.json().get('quotes', {}).get('quote', {})
    if isinstance(quote, list): quote = quote[0]
    last_price = float(quote.get('last', 0))
    
    cost_basis = float(target.get('cost_basis', 0))
    if cost_basis == 0: return False
    
    pnl_pct = ((last_price * float(target.get('quantity', 1))) - cost_basis) / cost_basis
    return pnl_pct >= threshold

def execute_trade(symbol, direction, qty=5):
    if "api.tradier.com" in os.getenv("TRADIER_BASE_URL", ""):
        return 403, "Production trade blocked"
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    option_symbol = get_atm_option_symbol(symbol, direction)
    if not option_symbol: return 400, "Lookup failed"
    order_data = {"class": "option", "option_symbol": option_symbol, "side": "buy_to_open" if direction == "CALL" else "short", "quantity": qty, "type": "market", "duration": "day"}
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    resp = requests.post(f"{base_url}/accounts/{account_id}/orders", data=order_data, headers=headers)
    return resp.status_code, resp.text

def force_exit_all(symbol, limit_price=None, force_market=False):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    # 1. Check for existing open orders for this symbol
    orders_resp = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers).json()
    orders = orders_resp.get('orders', {}).get('order', [])
    if isinstance(orders, dict): orders = [orders]
    if any(o.get('option_symbol') == symbol and o.get('status') == 'open' for o in orders):
        return "Order already pending."

    # 2. Proceed with exit if no open order
    pos_data = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers).json()
    positions = pos_data.get('positions', {}).get('position', [])
    if isinstance(positions, dict): positions = [positions]
    
    target = next((p for p in positions if p['symbol'] == symbol), None)
    if not target: return "No position found."
    
    actual_contract = target['symbol']
    # Use the specific contract symbol we found in the positions, don't fallback if we already have it
    
    order_data = {
        "class": "option",
        "option_symbol": actual_contract,
        "side": "sell_to_close",
        "quantity": str(int(float(target['quantity']))),
        "type": "market" if force_market else ("limit" if limit_price else "market"),
        "duration": "day"
    }
    if limit_price and not force_market: 
        order_data["price"] = limit_price
    
    resp = requests.post(f"{base_url}/accounts/{account_id}/orders", data=order_data, headers=headers)
    return f"Exit triggered: {resp.status_code} | Payload: {order_data} | Response: {resp.text}"

def cancel_order(order_id):
    """
    Explicitly cancels an open order on the Tradier Sandbox.
    """
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    print(f"[*] Dispatch: Sending DELETE request to cancel order {order_id}...")
    resp = requests.delete(f"{base_url}/accounts/{account_id}/orders/{order_id}", headers=headers)
    
    if resp.status_code == 200:
        print(f"[✓] Dispatch: Order {order_id} successfully cancelled.")
        return True
    else:
        print(f"[!] Dispatch: Cancel failed. Status: {resp.status_code} | Response: {resp.text}")
        return False

def submit_limit_exit(option_symbol, qty, limit_price):
    """
    Submits a fresh, targeted sell_to_close limit order to anchor to the new GEX level.
    """
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    order_data = {
        "class": "option",
        "option_symbol": option_symbol,
        "side": "sell_to_close",
        "quantity": str(int(float(qty))),
        "type": "limit",
        "price": f"{limit_price:.2f}",
        "duration": "day"
    }
    
    print(f"[*] Dispatch: Submitting exit limit order for {option_symbol} at ${limit_price:.2f}...")
    resp = requests.post(f"{base_url}/accounts/{account_id}/orders", data=order_data, headers=headers)
    
    if resp.status_code in [200, 201]:
        print(f"[✓] Dispatch: Exit order posted successfully. Response: {resp.text}")
        return True, resp.json()
    else:
        print(f"[!] Dispatch: Failed to post exit limit order: {resp.status_code} | {resp.text}")
        return False, resp.text
