import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def check_fill_history():
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    print("=" * 95)
    print(f"📜  HARM.AI // TRADIER HISTORICAL TRANSACTION & FILL PIPELINE")
    print("=" * 95)
    
    try:
        response = requests.get(f"{base_url}/accounts/{account_id}/history", headers=headers)
        if response.status_code != 200:
            print(f"[-] History retrieval failed: Status {response.status_code}")
            return

        json_data = response.json()
        history_data = json_data.get('history', {})
        if not history_data or history_data is None:
            print("[📝] No historical fills recorded.")
            return

        events = history_data.get('event', [])
        if not isinstance(events, list):
            events = [events]

        fmt_str = "{:<12} | {:<20} | {:<12} | {:<4} | {:<10} | {:<18}"
        print(fmt_str.format("Date", "Contract/Asset", "Type", "Qty", "Price", "Transaction ID"))
        print("-" * 95)

        for e in events:
            if not isinstance(e, dict):
                continue
            
            event_type = e.get('type', '')
            # Handle standard trade/option executions
            if event_type in ['trade', 'option']:
                date_str = e.get('date', 'N/A')[:10]  # Grab YYYY-MM-DD
                
                # Check for nested trade dictionary, fallback to direct event attributes
                details = e.get('trade', {})
                if not isinstance(details, dict):
                    details = e
                
                sym = details.get('symbol') or e.get('symbol') or 'N/A'
                qty = details.get('quantity') or e.get('quantity') or '0'
                price_val = details.get('price') or e.get('price') or 0.0
                
                try:
                    price_str = f"${float(price_val):.2f}"
                except (ValueError, TypeError):
                    price_str = "N/A"

                print(fmt_str.format(
                    date_str,
                    str(sym),
                    str(event_type).upper(),
                    str(qty),
                    price_str,
                    str(e.get('id', 'N/A'))
                ))
        print("-" * 95)

    except Exception as ex:
        print(f"[!] History check failed: {ex}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_fill_history()
