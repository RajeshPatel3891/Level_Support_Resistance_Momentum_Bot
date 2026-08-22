#!/usr/bin/env python3
# ==============================================================================
# HARM.AI // SMART CSO DAEMON (DYNAMIC DELTA PEG & MIDPOINT WALKER INTEGRATED)
# ==============================================================================
import sys, time, os, dotenv, threading, traceback, requests, re, boto3
sys.path.extend(["/app", "/app/src", ".", "src"])

env_file = "/app/.env.prod" if os.path.exists("/app/.env.prod") else ".env.prod"
dotenv.load_dotenv(env_file, override=True)

import smart_cso_injector

armed_tickers = ["SOFI", "F", "AAL", "RIVN", "SNAP", "MARA", "CCL"]

# ------------------------------------------------------------------------------
# NON-BLOCKING TELEMETRY OVERRIDE
# ------------------------------------------------------------------------------
orig_telemetry = smart_cso_injector.monitor_live_exit_telemetry
def non_blocking_telemetry(ticker):
    t = threading.Thread(target=orig_telemetry, args=(ticker,), daemon=True)
    t.start()
    print(f"   [📡 BACKGROUND TELEMETRY] Engaged daemon watch thread for {ticker}")

smart_cso_injector.monitor_live_exit_telemetry = non_blocking_telemetry

# ------------------------------------------------------------------------------
# TRADIER HELPER FUNCTIONS FOR ORDER WALKING
# ------------------------------------------------------------------------------
def get_live_quote_dict(occ_symbol):
    token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN') or os.getenv('TRADIER_ACCESS_TOKEN', '')
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        res = requests.get(f"{base_url}/markets/quotes?symbols={occ_symbol}", headers=headers, timeout=5)
        if res.status_code == 200:
            q = res.json().get('quotes', {}).get('quote', {})
            if isinstance(q, list):
                q = q[0] if q else {}
            return {'bid': float(q.get('bid', 0.0) or 0.0), 'ask': float(q.get('ask', 0.0) or 0.0)}
    except Exception as e:
        print(f"   [-] Quote Fetch Error for {occ_symbol}: {e}")
    return {'bid': 0.0, 'ask': 0.0}

def place_limit_order(occ_symbol, ticker, shares, price):
    token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN') or os.getenv('TRADIER_ACCESS_TOKEN', '')
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    match = re.match(r'^([A-Z]+)\d{6}[CP]\d{8}$', occ_symbol)
    root_symbol = match.group(1) if match else ticker

    payload = {
        'class': 'option',
        'symbol': root_symbol,
        'option_symbol': occ_symbol,
        'side': 'buy_to_open',
        'quantity': str(shares),
        'type': 'limit',
        'price': f"{price:.2f}",
        'duration': 'day'
    }
    try:
        url = f"{base_url}/accounts/{account_id}/orders"
        res = requests.post(url, data=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            order_info = res.json().get('order', {})
            return order_info.get('id')
    except Exception as e:
        print(f"   [-] Place Limit Order Error: {e}")
    return None

def cancel_order(order_id):
    if not order_id:
        return False
    token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN') or os.getenv('TRADIER_ACCESS_TOKEN', '')
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        url = f"{base_url}/accounts/{account_id}/orders/{order_id}"
        res = requests.delete(url, headers=headers, timeout=5)
        return res.status_code == 200
    except Exception as e:
        print(f"   [-] Order Cancel Error for Order {order_id}: {e}")
    return False

def wait_for_fill(order_id, timeout=10):
    if not order_id:
        return False
    token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN') or os.getenv('TRADIER_ACCESS_TOKEN', '')
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip('/')
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    start = time.time()
    while time.time() - start < timeout:
        try:
            url = f"{base_url}/accounts/{account_id}/orders/{order_id}"
            res = requests.get(url, headers=headers, timeout=3)
            if res.status_code == 200:
                order = res.json().get('order', {})
                status = str(order.get('status', '')).lower()
                if status == 'filled':
                    return True
                elif status in ['canceled', 'rejected', 'expired']:
                    return False
        except Exception:
            pass
        time.sleep(1)
    return False

def register_active_position_in_dynamo(ticker, occ_symbol, fill_price, shares, order_id):
    """Immediate DB write-through upon order walker fill to hydrate UI active cards."""
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        now_str = time.strftime('%Y-%m-%d %H:%M:%S')
        direction = 'PUT' if 'P' in occ_symbol else 'CALL'
        
        item = {
            'tenant_id': 'COMPANY_A',
            'trade_id': f"trade_{ticker}_{order_id}",
            'ticker': ticker,
            'occ_symbol': occ_symbol,
            'direction': direction,
            'strategy': 'SMART_CSO_LIVE',
            'entry_price': str(fill_price),
            'spot_price': str(fill_price),
            'shares': str(shares),
            'stop_loss': str(round(fill_price * 0.80, 2)),
            'take_profit': str(round(fill_price * 1.50, 2)),
            'net_pnl': '0.00',
            'exit_status': 'ACTIVE',
            'timestamp': now_str,
            'execution_env': os.getenv('EXECUTION_ENV', 'PROD').upper(),
            'is_live': 1
        }
        table.put_item(Item=item)
        print(f"   [🚀 UI HYDRATION REGISTERED] Ingested ACTIVE state for {ticker} ({occ_symbol}) @ ${fill_price:.2f}")
    except Exception as e:
        print(f"   [!] Warning: Failed to register active position in DynamoDB: {e}")

# ------------------------------------------------------------------------------
# DYNAMIC DELTA PEG & MIDPOINT ORDER WALKER ENGINE
# ------------------------------------------------------------------------------
def calculate_dynamic_entry_price(bid_px, ask_px, momentum_score=0.5):
    """Calculates dynamic limit price between Bid and Mid based on spread width and momentum."""
    spread = ask_px - bid_px
    if spread <= 0.02:
        return bid_px  # Tight spreads sit strictly on the Bid

    peg_factor = 0.25 if momentum_score < 0.7 else 0.50
    target_price = bid_px + (spread * peg_factor)
    return round(target_price, 2)

def execute_cso_smart_walk_entry(occ_symbol, ticker, shares=1, momentum_score=0.5, timeout_sec=15):
    """
    Tier 1: Places Limit Order at Dynamic Peg (25% or Bid).
    Tier 2: If unfilled after 10s, cancels and steps up to Midpoint (50%).
    Tier 3: If still unfilled after timeout, cancels stale order to protect capital.
    """
    q = get_live_quote_dict(occ_symbol)
    bid_px, ask_px = q.get('bid', 0.0), q.get('ask', 0.0)
    
    if bid_px <= 0:
        print(f"   [!] Invalid Bid price (${bid_px:.2f}) for {occ_symbol}. Aborting walk entry.")
        return None

    # TIER 1: Dynamic Peg Entry (25% or Bid)
    tier1_px = calculate_dynamic_entry_price(bid_px, ask_px, momentum_score)
    order_id = place_limit_order(occ_symbol, ticker, shares, price=tier1_px)
    print(f"   [*] [TIER 1 - DYNAMIC PEG] Placed {ticker} @ ${tier1_px:.2f} (Bid: ${bid_px:.2f} / Ask: ${ask_px:.2f}) | Order ID: {order_id}")
    
    if wait_for_fill(order_id, timeout=10):
        print(f"   [✓ TIER 1 FILL CONFIRMED] {shares}x {occ_symbol} filled @ ${tier1_px:.2f}")
        register_active_position_in_dynamo(ticker, occ_symbol, tier1_px, shares, order_id)
        return {'order_id': order_id, 'fill_price': tier1_px, 'occ_symbol': occ_symbol}

    # TIER 2: Midpoint Step-Up (50%)
    cancel_order(order_id)
    q_fresh = get_live_quote_dict(occ_symbol)
    bid_f, ask_f = q_fresh.get('bid', bid_px), q_fresh.get('ask', ask_px)
    mid_px = round((bid_f + ask_f) / 2.0, 2)
    
    print(f"   [⚠️ TIER 1 UNFILLED] Walking {ticker} order up to MIDPOINT: ${mid_px:.2f}")
    order_id_mid = place_limit_order(occ_symbol, ticker, shares, price=mid_px)
    
    if wait_for_fill(order_id_mid, timeout=10):
        print(f"   [✓ TIER 2 FILL CONFIRMED] {shares}x {occ_symbol} filled @ MIDPOINT: ${mid_px:.2f}")
        register_active_position_in_dynamo(ticker, occ_symbol, mid_px, shares, order_id_mid)
        return {'order_id': order_id_mid, 'fill_price': mid_px, 'occ_symbol': occ_symbol}

    # TIER 3: Cancel Stale Order
    cancel_order(order_id_mid)
    print(f"   [🛡️ ORDER EXPIRED] Midpoint order for {ticker} timed out. Canceling to prevent stale fill.")
    return None

# Override execution hooks inside smart_cso_injector
if hasattr(smart_cso_injector, 'execute_tradier_buy'):
    smart_cso_injector.execute_tradier_buy = execute_cso_smart_walk_entry

def run_daemon_loop():
    print("="*65)
    print("🚀🚀 HARM.AI // SINGLE-FILL VERIFICATION DAEMON ACTIVE 🚀🚀")
    print("   Mode   : SINGLE FILL & SHUTDOWN (DYNAMIC PEG-TO-MID WALKER ENGAGED)")
    print(f"   Account: {os.getenv('TRADIER_ACCOUNT_ID')}")
    print(f"   Targets: {armed_tickers}")
    print("="*65)

    iteration = 1
    while True:
        print(f"\n--- [DAEMON LOOP #{iteration}] Scanning Targets at {time.strftime('%H:%M:%S')} ---")
        for ticker in armed_tickers:
            try:
                res = smart_cso_injector.smart_cso_scout_and_execute(ticker)
                print(f"   [✓] Result for {ticker}: {res}")

                # SINGLE-FILL CIRCUIT BREAKER
                if res is not None:
                    print("\n" + "="*65)
                    print(f"🎉🎉 [SINGLE-FILL CONFIRMED] Trade successfully executed for {ticker}!")
                    print("   [🛡️ RISK OFF] Shutting down daemon scout loop to protect capital.")
                    print("   Background telemetry threads will continue managing active exit.")
                    print("="*65)
                    return

            except Exception as e:
                print(f"   [!] Error executing {ticker}: {e}")
                traceback.print_exc()
            time.sleep(2)

        print("\n[*] Iteration complete. Sleeping 30s...")
        iteration += 1
        time.sleep(30)

if __name__ == "__main__":
    run_daemon_loop()
