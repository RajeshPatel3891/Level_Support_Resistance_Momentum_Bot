import requests
import os
from dotenv import load_dotenv

load_dotenv()

def get_live_pnl(symbol):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    base_url = "https://sandbox.tradier.com/v1"

    # 1. Fetch Position to get cost_basis
    pos_resp = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers).json()
    positions = pos_resp.get('positions', {}).get('position', [])
    if isinstance(positions, dict): positions = [positions]
    
    pos = next((p for p in positions if p['symbol'] == symbol), None)
    if not pos: return None

    # 2. Fetch current Market Price
    quote_resp = requests.get(f"{base_url}/markets/quotes?symbols={symbol}", headers=headers).json()
    quote = quote_resp.get('quotes', {}).get('quote', {})
    # Handle case where quote might be a list or dict
    if isinstance(quote, list): quote = quote[0]
    last_price = float(quote.get('last', 0))

    # 3. Calculate
    qty = float(pos['quantity'])
    cost_basis = float(pos['cost_basis'])
    current_value = last_price * qty
    pnl = current_value - cost_basis
    
    return pnl

if __name__ == "__main__":
    symbol = "AAPL260717P00110000"
    pnl = get_live_pnl(symbol)
    if pnl is not None:
        print(f"Current PnL for {symbol}: ${pnl:.2f}")
    else:
        print(f"Position for {symbol} not found.")
