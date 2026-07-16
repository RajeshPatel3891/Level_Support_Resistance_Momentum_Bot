import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def audit_orders():
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    print("=" * 95)
    print(f"🕵️‍♂️  HARM.AI // TRADIER INTRADAY ORDER LOG AUDIT")
    print("=" * 95)
    
    try:
        # Get all orders (including filled, rejected, canceled) for today
        response = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers)
        if response.status_code != 200:
            print(f"[-] Failed to fetch orders: {response.status_code}")
            return
            
        data = response.json()
        orders_container = data.get('orders', {})
        if not orders_container or orders_container is None:
            print("[📝] No order logs found on the book for today.")
            return
            
        orders = orders_container.get('order', [])
        if not isinstance(orders, list):
            orders = [orders]
            
        fmt_str = "{:<12} | {:<22} | {:<12} | {:<4} | {:<10} | {:<12} | {:<20}"
        print(fmt_str.format("Order ID", "Contract", "Side", "Qty", "Price", "Status", "Created At"))
        print("-" * 115)
        
        for o in orders:
            # Focus on option contracts
            sym = o.get('option_symbol') or o.get('symbol', 'N/A')
            created = o.get('create_date', 'N/A')
            
            # Format limit price nicely
            price_val = o.get('price')
            price_str = f"${float(price_val):.2f}" if price_val else "MKT"
            
            print(fmt_str.format(
                str(o.get('id', 'N/A')),
                str(sym),
                str(o.get('side', 'N/A')).upper(),
                str(o.get('quantity', 'N/A')),
                price_str,
                str(o.get('status', 'N/A')).upper(),
                str(created)
            ))
        print("-" * 115)
        
    except Exception as e:
        print(f"[!] Audit failed: {e}")

if __name__ == "__main__":
    audit_orders()
