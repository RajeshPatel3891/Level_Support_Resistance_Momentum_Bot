import os
import sys
import time
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Define preset dynamic risk regimes
RISK_PRESETS = {
    'scalping': {
        'tp_pct': 0.004,      # 0.4% target
        'sl_pct': 0.002,      # 0.2% stop
        'desc': 'Tight Scalping (Intraday Levels)'
    },
    'normal': {
        'tp_pct': 0.01,       # 1.0% target
        'sl_pct': 0.005,      # 0.5% stop
        'desc': 'Standard Daily Trend Monitor'
    },
    'high_volatility': {
        'tp_pct': 0.03,       # 3.0% target
        'sl_pct': 0.015,      # 1.5% stop
        'desc': 'High Volatility (Earnings / Momentum Breaks)'
    }
}

def get_live_quote(symbol, headers):
    url = f"https://sandbox.tradier.com/v1/markets/quotes?symbols={symbol}"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        return r.json().get('quotes', {}).get('quote', {})
    return {}

def run_risk_daemon(symbol="NVDA", regime="normal", poll_interval=3):
    """
    Actively polls position and live prices every `poll_interval` seconds
    to enforce Take-Profit and dynamic Trailing Stop-Loss brackets immediately.
    """
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    # Load parameters from selected preset
    preset = RISK_PRESETS.get(regime, RISK_PRESETS['normal'])
    tp_pct = preset['tp_pct']
    sl_pct = preset['sl_pct']

    print("=" * 95)
    print(f"🛡️  HARM.AI // ACTIVE REAL-TIME RISK DAEMON STARTED")
    print(f"[*] Target: {symbol} | Mode: {regime.upper()} ({preset['desc']})")
    print(f"[*] Rules: Take Profit: +{tp_pct*100:.2f}% | Trailing Stop: -{sl_pct*100:.2f}% | Poll Rate: {poll_interval}s")
    print("=" * 95)

    # State tracking variables for trailing stops
    peak_price = 0.0

    try:
        while True:
            # 1. Fetch current open positions
            pos_resp = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers)
            if pos_resp.status_code != 200:
                print("[-] Connection drop. Retrying next cycle...")
                time.sleep(poll_interval)
                continue

            pos_data = pos_resp.json().get('positions', {}) or {}
            positions = pos_data.get('position', []) if pos_data else []
            if not isinstance(positions, list):
                positions = [positions]

            active_pos = next((p for p in positions if p.get('symbol') == symbol), None)

            # If the position has been closed out, we terminate the daemon
            if not active_pos:
                print(f"\n[✨] Position completely flat on {symbol}. Risk loop terminating successfully.")
                break

            qty = int(float(active_pos.get('quantity', 0.0)))
            cost_basis = float(active_pos.get('cost_basis', 0.0))

            # 2. Pull current live market ticks
            quote = get_live_quote(symbol, headers)
            if not quote:
                time.sleep(poll_interval)
                continue

            last_price = float(quote.get('last', 0.0))

            # Initialize peak price if not yet set
            if peak_price == 0.0:
                peak_price = max(cost_basis, last_price)

            # 3. Dynamic Trailing Stop-Loss calculation
            # If price hits a new high, raise our stop-loss floor
            if last_price > peak_price:
                peak_price = last_price

            tp_price = round(cost_basis * (1 + tp_pct), 2)
            sl_price = round(peak_price * (1 - sl_pct), 2)

            unrealized_pnl = (last_price - cost_basis) * qty
            pnl_pct = ((last_price - cost_basis) / cost_basis) * 100

            # Dynamic Print Update showing current Peak and trailing boundaries
            sys.stdout.write(
                f"\r[*] {symbol} Price: ${last_price:.2f} | Basis: ${cost_basis:.2f} | Peak: ${peak_price:.2f} | "
                f"P&L: {pnl_pct:+.2f}% (${unrealized_pnl:+.2f}) | "
                f"Bounds: [SL ${sl_price:.2f} <-> TP ${tp_price:.2f}]"
            )
            sys.stdout.flush()

            # 4. Trigger Checks
            if last_price >= tp_price:
                print(f"\n[🎯] TAKE PROFIT TARGET REACHED (${tp_price:.2f})! Executing exit...")
                execute_fast_exit(base_url, account_id, symbol, qty, headers)
                break
            elif last_price <= sl_price:
                print(f"\n[🚨] TRAILING STOP BREACHED (${sl_price:.2f})! Executing defensive exit...")
                execute_fast_exit(base_url, account_id, symbol, qty, headers)
                break

            time.sleep(poll_interval)

    except KeyboardInterrupt:
        print("\n[-] Risk daemon stopped manually via terminal command.")
    except Exception as e:
        print(f"\n[!] Daemon encountered error: {e}")

def execute_fast_exit(base_url, account_id, symbol, qty, headers):
    payload = {
        'class': 'equity',
        'symbol': symbol,
        'side': 'sell',
        'quantity': str(qty),
        'type': 'market',
        'duration': 'day'
    }
    r = requests.post(f"{base_url}/accounts/{account_id}/orders", data=payload, headers=headers)
    if r.status_code == 200:
        print(f"[✓] Exited {qty} shares of {symbol} via Market Order ID: {r.json().get('order', {}).get('id')}")
    else:
        print(f"[-] Exit failure: {r.text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HARM.AI Dynamic Position Safety Guardian Daemon")
    parser.add_argument("--symbol", type=str, default="NVDA", help="Asset ticker to manage")
    parser.add_argument("--regime", type=str, choices=["scalping", "normal", "high_volatility"], default="normal", help="Regime preset selection")
    parser.add_argument("--poll", type=int, default=3, help="Poll interval in seconds")
    args = parser.parse_args()

    run_risk_daemon(symbol=args.symbol, regime=args.regime, poll_interval=args.poll)
