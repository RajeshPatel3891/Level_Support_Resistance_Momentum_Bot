import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def reconcile():
    # 1. Get Live Data
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    pos_resp = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers).json()
    positions = pos_resp.get('positions', {}).get('position', [])
    if isinstance(positions, dict): positions = [positions]

    # 2. Robust Manifest Search
    manifest_path = 'trading_levels.json'
    if not os.path.exists(manifest_path):
        manifest_path = 'trading_levels.json'
        
    with open(manifest_path, 'r') as f:
        manifest = json.load(f).get('levels', {})

    print(f"\n{'='*55}\n HARM.AI // POSITION RECONCILIATION \n{'='*55}")
    for pos in positions:
        ticker = pos['symbol']
        entry_basis = float(pos['cost_basis']) / float(pos['quantity'])
        
        # Pull context from manifest
        meta = manifest.get(ticker, {})
        print(f"[{ticker}] Qty: {pos['quantity']} | Entry: {entry_basis:.2f}")
        print(f"    • Institutional Support: {meta.get('algo_macro', {}).get('support', 'N/A')}")
        print(f"    • Tactical Modifier: {meta.get('human_tactical', {}).get('breakdown_trigger', 'N/A')}")
        print(f"    • Current PnL: {pos.get('open_pl', 'N/A')}")
        print('-'*55)

if __name__ == "__main__":
    reconcile()
