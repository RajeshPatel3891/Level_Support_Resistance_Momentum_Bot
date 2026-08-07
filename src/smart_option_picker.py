import os
import sys
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def get_closest_expiration(symbol, headers):
    """Fetches valid option expiration dates for the symbol and returns the nearest one."""
    url = f"https://sandbox.tradier.com/v1/markets/options/expirations?symbol={symbol}"
    r = requests.get(url, headers=headers)
    if r.status_code == 200:
        exp_data = r.json().get('expirations', {})
        if exp_data and exp_data.get('date'):
            dates = exp_data['date']
            return dates if isinstance(dates, list) else [dates]
    return []

def find_best_liquid_option(symbol="NVDA", option_type="call", target_strike=None, max_spread_pct=0.15, min_open_interest=100):
    """
    Scans the options chain for the nearest expiration and finds the contract closest to target_strike
    that passes strict liquidity criteria.
    """
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    print("=" * 95)
    print(f"🎯  HARM.AI // OPTION SELECTION & LIQUIDITY GUARD ENGINE")
    print("=" * 95)

    # 1. Fetch nearest expiration date
    expirations = get_closest_expiration(symbol, headers)
    if not expirations:
        print("[-] No valid option expirations found.")
        return None
    
    target_exp = expirations[0] # Pick the front-month / weekly expiration
    print(f"[*] Target Expiration Selected: {target_exp}")

    # 2. Fetch Option Chain for expiration
    chain_url = f"{base_url}/markets/options/chains?symbol={symbol}&expiration={target_exp}"
    chain_resp = requests.get(chain_url, headers=headers)
    if chain_resp.status_code != 200:
        print(f"[-] Failed to retrieve options chain: {chain_resp.status_code}")
        return None

    chain_data = chain_resp.json().get('options', {}) or {}
    options_list = chain_data.get('option', []) if chain_data else []
    if not isinstance(options_list, list):
        options_list = [options_list]

    # If no target strike specified, fetch stock price and pick at-the-money
    if not target_strike:
        quote_r = requests.get(f"{base_url}/markets/quotes?symbols={symbol}", headers=headers)
        if quote_r.status_code == 200:
            stock_price = float(quote_r.json().get('quotes', {}).get('quote', {}).get('last', 0.0))
            target_strike = stock_price
            print(f"[*] Stock Price ATM Target: ${stock_price:.2f}")

    # 3. Filter Chain based on Liquidity Guidelines
    valid_candidates = []
    print(f"[*] Auditing chain for liquid {option_type.upper()} options near ${target_strike:.2f} strike...")
    
    for opt in options_list:
        if opt.get('option_type') != option_type:
            continue

        strike = float(opt.get('strike', 0.0))
        bid = float(opt.get('bid', 0.0))
        ask = float(opt.get('ask', 0.0))
        oi = int(opt.get('open_interest', 0))
        opt_symbol = opt.get('symbol')

        # Midpoint calculations
        midpoint = (bid + ask) / 2
        spread = ask - bid
        spread_pct = (spread / midpoint) if midpoint > 0 else float('inf')

        # Standard Liquidity Filters
        if bid <= 0.05: # Filter out raw zero-bid options
            continue
        if spread_pct > max_spread_pct: # Filter out wide spreads
            continue
        if oi < min_open_interest: # Ensure some open market depth exists
            continue

        valid_candidates.append({
            'symbol': opt_symbol,
            'strike': strike,
            'bid': bid,
            'ask': ask,
            'spread_pct': spread_pct,
            'open_interest': oi,
            'midpoint': midpoint,
            'distance': abs(strike - target_strike)
        })

    if not valid_candidates:
        print("[🚨] LIQUIDITY CRITICAL: No contracts passed the safety filters. Execution aborted.")
        return None

    # Sort first by distance to target strike, then by tightest spread pct
    valid_candidates.sort(key=lambda x: (x['distance'], x['spread_pct']))
    best_contract = valid_candidates[0]

    print("\n[✓] Safety Audit Passed! Best Liquid Option Located:")
    print("-" * 95)
    print(f"  Option Symbol:  {best_contract['symbol']}")
    print(f"  Strike Price:   ${best_contract['strike']:.2f} (Dist: ${best_contract['distance']:.2f})")
    print(f"  Bid / Ask:      ${best_contract['bid']:.2f} / ${best_contract['ask']:.2f} (Spread: {best_contract['spread_pct']*100:.1f}%)")
    print(f"  Open Interest:  {best_contract['open_interest']} contracts")
    print("-" * 95)

    return best_contract

if __name__ == "__main__":
    find_best_liquid_option()
