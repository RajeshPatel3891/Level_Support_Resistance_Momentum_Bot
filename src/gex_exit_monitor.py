import os
import json
import time
import traceback
import requests
import sys
from dotenv import load_dotenv

# Force absolute parent tracking to resolve 'from src.X import Y' flawlessly
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from src.HarmonizedDispatch import force_exit_all, get_position_pnl, cancel_order, submit_limit_exit
from src.GexGateway import GexGateway
from src.smart_option_picker import find_best_liquid_option

load_dotenv()

DRIFT_THRESHOLD = 0.50  # Drift threshold in dollars before executing Cancel & Replace

# Local memory lock to prevent double-execution while orders are filling
EXECUTED_EXITS = set()

MANIFEST_PATH = os.path.join(parent_dir, 'trading_levels.json')
if not os.path.exists(MANIFEST_PATH):
    MANIFEST_PATH = os.path.join(current_dir, 'trading_levels.json')

def get_headers():
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    return {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

def get_positions():
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    try:
        response = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=get_headers())
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and 'positions' in data:
                pos = data['positions'].get('position', [])
                return pos if isinstance(pos, list) else [pos]
        return []
    except Exception:
        return []

def get_open_orders():
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    try:
        response = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=get_headers())
        if response.status_code == 200:
            orders_data = response.json().get('orders', {})
            if not orders_data:
                return []
            orders = orders_data.get('order', [])
            return orders if isinstance(orders, list) else [orders]
        return []
    except Exception:
        return []

def get_current_price(symbol):
    base_url = "https://sandbox.tradier.com/v1"
    try:
        response = requests.get(f"{base_url}/markets/quotes?symbols={symbol}", headers=get_headers())
        if response.status_code == 200:
            data = response.json()
            quote = data.get('quotes', {}).get('quote', {})
            if isinstance(quote, list): quote = quote[0]
            return float(quote.get('last', 0))
    except Exception:
        return None
    return None

def monitor_gex_exits():
    global EXECUTED_EXITS
    print(f"[*] Harmonized GEX Exit Monitor: Active with Cancel & Replace Drift Tracking.")
    print(f"[*] Target Manifest Path: {MANIFEST_PATH}")
    gex_gateway = GexGateway()
    
    while True:
        try:
            levels = {}
            if os.path.exists(MANIFEST_PATH):
                with open(MANIFEST_PATH, 'r') as f:
                    levels = json.load(f)
            
            positions = get_positions()
            open_orders = get_open_orders()
            
            # Clean up memory lock: Remove contracts we no longer physically hold
            active_symbols = {pos.get('symbol') for pos in positions if pos.get('symbol')}
            EXECUTED_EXITS = EXECUTED_EXITS.intersection(active_symbols)
            
            for pos in positions:
                ticker = pos.get('symbol', '')  # e.g., "QQQ260717C00710000" or "NVDA"
                if not ticker:
                    continue
                
                # SPREAD CONTROL: Bypass monitor entirely if asset class is equity stock
                if len(ticker) <= 6:
                    continue
                
                # If we've already dispatched a force exit on this contract, skip to protect API
                if ticker in EXECUTED_EXITS:
                    print(f"[⚙️] GEX MONITOR: Exit already dispatched for {ticker}. Lock active. Awaiting broker clearance...")
                    continue
                
                underlying = "".join([c for c in ticker if c.isalpha()])
                if "AAPL" in underlying: underlying = "AAPL"
                
                # 1. Fetch dynamic, fresh GEX Flip level from FlashAlpha
                gex_flip = None
                try:
                    gex_data = gex_gateway.get_gex_levels(underlying)
                    if gex_data and 'levels' in gex_data:
                        gex_flip = float(gex_data['levels'].get('gamma_flip', 0))
                except Exception as ex_gex:
                    print(f"[-] GEX MONITOR: FlashAlpha lookup failed: {ex_gex}. Testing local fallback.")
                
                # 2. Fallback to live Tradier data on 429 quota exceptions, completely removing mock values
                if not gex_flip:
                    print("[⚙️] GEX MONITOR: Rate-Limit Fallback active. Sourcing premium context from Tradier instead.")
                    live_premium = get_current_price(ticker)
                    if live_premium is not None and live_premium > 0:
                        gex_flip = float(live_premium)
                    else:
                        # Fallback structural map data if quotes hit network limits
                        ticker_data = levels.get(underlying, {})
                        static_trigger = ticker_data.get('support_a') or ticker_data.get('human_tactical', {}).get('breakout_trigger')
                        if static_trigger:
                            gex_flip = float(static_trigger)
                        else:
                            gex_flip = 0.04  # Baseline option premium placeholder rather than $313 index values
                
                if not gex_flip:
                    print(f"[-] GEX MONITOR: No live or static Flip level available for {underlying}. Skipping cycle.")
                    continue
                
                # Check for absolute breach condition to run force-exit
                current_price = get_current_price(underlying)
                if current_price and current_price >= float(gex_flip):
                    print(f"[!] ALERT: Breach at {current_price}. Calling force_exit_all...")
                    try:
                        EXECUTED_EXITS.add(ticker)
                        is_profitable = get_position_pnl(ticker, threshold=0.0)
                        print(f"[*] Position PnL check: Profitable={is_profitable}")
                        
                        exit_result = force_exit_all(ticker, limit_price=gex_flip, force_market=is_profitable)
                        print(f"[*] Exit command executed: {exit_result}")
                    except Exception:
                        print("[!] CRITICAL: force_exit_all failed. Releasing lock.")
                        EXECUTED_EXITS.discard(ticker)
                        traceback.print_exc()
                    continue
                
                # 3. Evaluate active limit order drift
                active_order = next(
                    (o for o in open_orders if o.get('option_symbol') == ticker and o.get('status') in ['open', 'pending', 'accepted']),
                    None
                )
                
                if active_order:
                    current_order_price = float(active_order.get('price', 0.0))
                    order_id = active_order.get('id')
                    
                    # 4. Drift Detection State Machine
                    drift_delta = abs(current_order_price - gex_flip)
                    print(f"DEBUG: Ticker: {ticker} | Order Price: ${current_order_price:.2f} | GEX Flip: ${gex_flip:.2f} | Drift: ${drift_delta:.2f}")
                    
                    if drift_delta > DRIFT_THRESHOLD:
                        print(f"[🚨 DRIFT DETECTED 🚨] Drift of ${drift_delta:.2f} exceeds threshold of ${DRIFT_THRESHOLD:.2f}.")
                        
                        # 5. Execute Cancel-Replace sequence
                        cancel_success = cancel_order(order_id)
                        if cancel_success:
                            time.sleep(1.0)
                            qty = float(pos.get('quantity', 1))
                            submit_limit_exit(ticker, qty, gex_flip)
                else:
                    # Leverage Option Picker before laying down baseline orders
                    is_bullish = ("C" in ticker)  # Fallback type detection logic
                    print("[🔥] Level active! Activating Liquidity Guard check before routing baseline orders...")
                    target_option = find_best_liquid_option(
                        symbol=underlying,
                        option_type="call" if is_bullish else "put",
                        max_spread_pct=0.15,
                        min_open_interest=100
                    )
                    
                    if target_option:
                        opt_symbol = target_option['symbol']
                        print(f"[🚀] Routing baseline limit order for verified liquid contract: {opt_symbol}")
                        qty = float(pos.get('quantity', 1))
                        submit_limit_exit(opt_symbol, qty, gex_flip)
                    else:
                        print(f"[🚨] GEX MONITOR: Option picker rejected asset {ticker} chain due to bad liquidity parameters.")
                        
        except Exception as e:
            print(f"[!] Error in monitoring loop: {e}")
            traceback.print_exc()
            
        time.sleep(15)

if __name__ == "__main__":
    monitor_gex_exits()
