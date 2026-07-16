import requests
import os

# Config from environment
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL")
ACCESS_TOKEN = os.getenv("TRADIER_ACCESS_TOKEN")
ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")

def clear_positions():
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Accept": "application/json"}
    
    # 1. Fetch positions
    response = requests.get(f"{TRADIER_BASE_URL}/accounts/{ACCOUNT_ID}/positions", headers=headers)
    data = response.json()
    positions = data.get('positions', {}).get('position', [])
    if isinstance(positions, dict): positions = [positions]
    
    # 2. Iterate and sell
    for pos in positions:
        # For options, we need the underlying symbol for 'symbol' 
        # and the OCC symbol for 'option_symbol'
        occ_symbol = pos.get('symbol') 
        qty = pos.get('quantity')
        
        # Simple heuristic to extract underlying from OCC (e.g., SPY26... -> SPY)
        # Or if the API provides it in a separate field; here we assume the symbol is the OCC
        underlying = "".join([c for c in occ_symbol if not c.isdigit()]).split('P')[0].split('C')[0]
        
        print(f"Closing {occ_symbol} (Qty: {qty})")
        
        order_data = {
            "account_id": ACCOUNT_ID,
            "class": "option",
            "symbol": underlying,        # The underlying ticker
            "option_symbol": occ_symbol, # The specific OCC option contract
            "side": "sell_to_close",
            "quantity": str(int(float(qty))),
            "type": "market",
            "duration": "day"
        }
        
        order_resp = requests.post(f"{TRADIER_BASE_URL}/accounts/{ACCOUNT_ID}/orders", headers=headers, data=order_data)
        print(f"Order status: {order_resp.status_code} - {order_resp.text}")

if __name__ == "__main__":
    clear_positions()
