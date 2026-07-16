import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def check_position_pnl():
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    print("=" * 95)
    print(f"📈  HARM.AI // TRADIER LIVE UNREALIZED POSITION P&L MONITOR (FILTERED)")
    print("=" * 95)
    
    try:
        response = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers)
        if response.status_code != 200:
            print(f"[-] Broker connection error: Status {response.status_code}")
            return

        pos_data = response.json().get('positions', {})
        if not pos_data or pos_data is None:
            print("[📝] No live exposure found. All contracts are flat.")
            return

        positions = pos_data.get('position', [])
        if not isinstance(positions, list):
            positions = [positions]

        # Formatting table structure
        fmt_str = "{:<20} | {:<4} | {:<12} | {:<12} | {:<14} | {:<12}"
        print(fmt_str.format("Option Contract", "Qty", "Cost Basis", "Last Price", "Market Value", "Total P&L"))
        print("-" * 95)

        visible_positions = 0
        for p in positions:
            symbol = p.get('symbol', 'N/A')
            qty = float(p.get('quantity', 0.0))
            cost_basis = float(p.get('cost_basis', 0.0))
            
            # --- IGNORE GHOST TRADES ---
            # Any stale option position with an impossibly high cost basis ($25.00) is filtered out
            if cost_basis >= 25.00 and "AAPL" in symbol:
                continue

            visible_positions += 1
            quote_resp = requests.get(f"{base_url}/markets/quotes?symbols={symbol}", headers=headers)
            last_price = 0.0
            if quote_resp.status_code == 200:
                q_data = quote_resp.json().get('quotes', {}).get('quote', {})
                if isinstance(q_data, list): q_data = q_data[0]
                last_price = float(q_data.get('last', 0.0))

            multiplier = 100 if len(symbol) > 6 else 1
            total_cost = cost_basis
            current_value = qty * last_price * multiplier
            
            if cost_basis < 100 and multiplier == 100:
                total_cost = cost_basis * qty * multiplier

            unrealized_pnl = current_value - total_cost
            pnl_flag = f"+${unrealized_pnl:.2f}" if unrealized_pnl >= 0 else f"-${abs(unrealized_pnl):.2f}"

            print(fmt_str.format(
                str(symbol),
                str(int(qty)),
                f"${cost_basis / (multiplier if cost_basis > 100 else 1):.2f}",
                f"${last_price:.2f}",
                f"${current_value:.2f}",
                pnl_flag
            ))
            
        if visible_positions == 0:
            print("[📝] All active positions are filtered/flat. No fresh trades detected.")
        print("-" * 95)

    except Exception as e:
        print(f"[!] Target calculation failure: {e}")

if __name__ == "__main__":
    check_position_pnl()
