import os
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

# Force absolute path tracking
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def wipe_sandbox_clean():
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    print("=" * 95)
    print(f"🧹  HARM.AI // TRADIER SANDBOX PORTFOLIO SANITATION UTILITY")
    print("=" * 95)
    
    try:
        # Step 1: Cancel any active open orders that are locking up your assets
        print("[*] Auditing open order book for pending blocks...")
        orders_resp = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers)
        
        if orders_resp.status_code == 200:
            orders_data = orders_resp.json().get('orders', {})
            if orders_data and orders_data is not None:
                orders = orders_data.get('order', [])
                if not isinstance(orders, list):
                    orders = [orders]
                
                canceled_count = 0
                for o in orders:
                    if o.get('status') in ['open', 'pending', 'accepted']:
                        order_id = o.get('id')
                        cancel_resp = requests.delete(f"{base_url}/accounts/{account_id}/orders/{order_id}", headers=headers)
                        if cancel_resp.status_code == 200:
                            print(f"  [+] Terminated blocked order ID: {order_id}")
                            canceled_count += 1
                if canceled_count > 0:
                    print(f"[*] Cleared {canceled_count} orders. Giving the broker 1 second to update...")
                    time.sleep(1.0)
            else:
                print("  [✓] No blocking orders detected.")

        # Step 2: Fetch all lingering open positions
        print("[*] Retrieving active inventory ledger...")
        pos_resp = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers)
        if pos_resp.status_code != 200:
            print(f"[-] Failed to fetch positions: Status {pos_resp.status_code}")
            return

        pos_data = pos_resp.json().get('positions', {})
        if not pos_data or pos_data is None:
            print("\n[✓] CLEAN SLATE: Zero (0) open positions found. Your account is already completely flat!")
            return

        positions = pos_data.get('position', [])
        if not isinstance(positions, list):
            positions = [positions]

        print(f"[*] Found {len(positions)} lingering ghost assets. Initiating forced market liquidations...")
        
        for p in positions:
            symbol = p.get('symbol', '')
            qty = float(p.get('quantity', 0.0))
            if qty == 0:
                continue

            # Route closing payload based on whether it is an option or direct equity
            is_option = len(symbol) > 6
            payload = {
                'class': 'option' if is_option else 'equity',
                'symbol': "".join([c for c in symbol if c.isalpha()]) if is_option else symbol,
                'side': 'sell_to_close' if is_option else 'sell',
                'quantity': str(int(abs(qty))),
                'type': 'market',
                'duration': 'day'
            }
            if is_option:
                payload['option_symbol'] = symbol

            liquidate_resp = requests.post(f"{base_url}/accounts/{account_id}/orders", data=payload, headers=headers)
            
            if liquidate_resp.status_code == 200:
                order_id = liquidate_resp.json().get('order', {}).get('id')
                print(f"  [✓] Liquidated {qty} of {symbol} via Market order ID: {order_id}")
            else:
                print(f"  [-] Liquidation failed for {symbol}: {liquidate_resp.text}")

        print("\n[✓] All liquidation commands successfully dispatched. Giving the sandbox 2 seconds to settle...")
        time.sleep(2.0)
        
        # Verify clean slate
        verify_resp = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers)
        v_data = verify_resp.json().get('positions', {})
        if not v_data or v_data is None:
            print("[✨] Success! All ghost positions successfully wiped. Your portfolio is 100% clean!")
        else:
            print("[!] Warning: Some positions may still be settling with the broker. Run view_pnl.py to verify.")

    except Exception as e:
        print(f"[!] Cleanup failed: {e}")

if __name__ == "__main__":
    wipe_sandbox_clean()
