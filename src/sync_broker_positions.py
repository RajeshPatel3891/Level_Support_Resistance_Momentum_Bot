import os
import requests
from dotenv import load_dotenv

load_dotenv()

def reconcile_broker_slate():
    print("[*] Running Broker Slate Reconciliation...")
    token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN')
    acc_id = os.getenv('TRADIER_ACCOUNT_ID')
    if not token or not acc_id:
        print("[!] Tradier credentials missing. Skipping broker sync.")
        return

    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        res = requests.get(f"https://sandbox.tradier.com/v1/accounts/{acc_id}/positions", headers=headers, timeout=5)
        if res.status_code != 200:
            print(f"[!] Failed to fetch broker positions: {res.text}")
            return
            
        data = res.json().get('positions', {})
        if not data or data == 'null':
            print("[*] Active Broker Positions Found: []")
            return

        positions = data.get('position', [])
        if isinstance(positions, dict):
            positions = [positions]
        elif not isinstance(positions, list):
            positions = []
            
        broker_symbols = {p.get('symbol') for p in positions if p and isinstance(p, dict) and float(p.get('quantity', 0)) != 0}
        print(f"[*] Active Broker Positions Found: {list(broker_symbols)}")
        
    except Exception as e:
        print(f"[!] Reconciliation error: {e}")

if __name__ == '__main__':
    reconcile_broker_slate()
