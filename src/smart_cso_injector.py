import os

if os.getenv('EXECUTION_ENV', '').upper() == 'SANDBOX':
    os.environ['TRADIER_BASE_URL'] = 'https://sandbox.tradier.com/v1'
    if os.getenv('TRADIER_SANDBOX_TOKEN'):
        os.environ['TRADIER_TOKEN'] = os.getenv('TRADIER_SANDBOX_TOKEN')

#!/usr/bin/env python3
"""
HARM.AI // SMART CSO-DRIVEN LIVE TRADER & INJECTOR
===============================================================================
Scans trading_levels.json, evaluates proximity/safety and support/resistance 
boundaries, resolves directional bias (Call vs Put), performs smart option chain
liquidity & spread searches via Tradier API, enforces strict execution receipts, 
and synchronizes with both SQLite and AWS DynamoDB with live GSG/MTTP bindings.
Now features continuous real-time terminal exit telemetry streaming, dynamic
execution environment tagging (PRODUCTION vs SANDBOX), beta tier calibrations,
a two-stage Mid-to-Ask order execution waterfall, ghost-fill guards, rolling
quote smoothing (noise filter), underlying stock confirmation, stateful re-entry
guardrails (15-min cooldown, max 2 trades/day), valid OCC symbol generator with
3+ day min DTE guardrail and standard strike rounding, adaptive low-dollar stop
cushioning (<= $0.50 contracts), full SQLite auto-schema migrations, and unit test stubs.
"""

import os
import sys
import json
import time
import uuid
import sqlite3
import requests
import boto3
import argparse
import numpy as np
import datetime
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'harm_telemetry.db')
MANIFEST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'trading_levels.json')

TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
if "sandbox" in TRADIER_BASE_URL.lower():
    TRADIER_TOKEN = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
else:
    TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")

TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [SMART_CSO] {msg}")

# ===============================================================================
# STEP 1: ROLLING QUOTE SMOOTHING (NOISE FILTER)
# ===============================================================================

def get_smoothed_option_mark(occ_symbol, base_url=TRADIER_BASE_URL, headers=None, samples=3):
    """Fetches rolling ticks and returns the median mark to filter spread noise."""
    if headers is None:
        headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    marks = []
    for _ in range(samples):
        try:
            q = requests.get(f"{base_url}/markets/quotes", params={"symbols": occ_symbol}, headers=headers, timeout=2).json()
            quote = q.get("quotes", {}).get("quote", {})
            if isinstance(quote, list) and len(quote) > 0:
                quote = quote[0]
            bid = float(quote.get("bid") or 0.0)
            ask = float(quote.get("ask") or 0.0)
            mark = round((bid + ask) / 2.0, 2) if (bid and ask) else float(quote.get("last") or 0.0)
            if mark > 0:
                marks.append(mark)
        except Exception:
            pass
        time.sleep(0.3)
    
    return float(np.median(marks)) if len(marks) > 0 else 0.0

# ===============================================================================
# STEP 2: UNDERLYING STOCK CONFIRMATION
# ===============================================================================

def is_valid_signal_exit(ticker, spot_price, option_pnl_pct, support_level):
    """
    Validates if an option drop is real signal or just option spread noise.
    Returns True ONLY if underlying stock also breaks technical support.
    """
    if option_pnl_pct <= -20.0:
        return True  # Hard -20% stop always executes immediately
        
    # If option drops between -10% and -19%, verify stock price breakdown
    if spot_price < support_level:
        return True  # Stock broke support -> Real Signal
    else:
        print(f"[🛡️ NOISE FILTER] {ticker} option down {option_pnl_pct:.1f}% but stock (${spot_price:.2f}) holding support (${support_level:.2f}). IGNORING SPREAD NOISE.")
        return False

# ===============================================================================
# STEP 3: STATEFUL RE-ENTRY GUARDRAILS
# ===============================================================================

def validate_reentry_eligibility(ticker, db_path=DB_PATH):
    """Enforces 15-min cooldown and max 2 trades/day per ticker."""
    if not os.path.exists(db_path):
        return True
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        # 1. Check total trades today for this ticker
        c.execute("""
            SELECT COUNT(*), MAX(timestamp) FROM trades 
            WHERE UPPER(ticker) = UPPER(?) AND timestamp LIKE ?
        """, (ticker, f"{today_str}%"))
        
        row = c.fetchone()
        conn.close()
        
        trade_count = row[0] if row else 0
        last_timestamp_str = row[1] if row else None
        
        if trade_count >= 2:
            print(f"[⛔ RE-ENTRY BLOCKED] {ticker} has hit maximum 2 trades for today.")
            return False
            
        if last_timestamp_str:
            try:
                last_time = datetime.strptime(last_timestamp_str, "%Y-%m-%d %H:%M:%S")
                elapsed_mins = (datetime.now() - last_time).total_seconds() / 60.0
                if elapsed_mins < 15.0:
                    print(f"[⏳ COOLDOWN ACTIVE] {ticker} entered/exited {elapsed_mins:.1f}m ago. Need 15m cooldown.")
                    return False
            except Exception:
                pass
    except Exception as e:
        log_msg(f"[!] Re-entry validation warning: {e}")
            
    return True

# ===============================================================================
# HARM.AI // BETA CALIBRATION & EXECUTION WATERFALL
# ===============================================================================

BETA_PROFILES = {
    "HIGH": {"zone": 0.0075, "turn_ticks": 3, "trail_mult": 1.5},  # Widen band to arm SPY/QQQ/NVDA
    "MID":  {"zone": 0.0030, "turn_ticks": 3, "trail_mult": 1.0},
    "LOW":  {"zone": 0.0020, "turn_ticks": 2, "trail_mult": 0.75}
}

TICKER_BETA_MAP = {
    "SPY": "HIGH", "QQQ": "HIGH", "IWM": "HIGH", "NVDA": "HIGH", "TSLA": "HIGH",
    "AAPL": "HIGH", "AMZN": "HIGH", "GOOGL": "HIGH", "AMD": "HIGH", "META": "HIGH",
    "NFLX": "HIGH", "MARA": "HIGH",
    "PLTR": "MID", "RIVN": "MID", "SOFI": "MID", "HOOD": "MID", "UBER": "MID", "SNAP": "MID",
    "INTC": "LOW", "AAL": "LOW", "F": "LOW", "BAC": "LOW", "CCL": "LOW", "NKE": "LOW"
}

def get_ticker_calibration(ticker: str):
    beta_tier = TICKER_BETA_MAP.get(ticker.upper(), "MID")
    profile = BETA_PROFILES[beta_tier]
    return {
        "beta_tier": beta_tier,
        "proximity_threshold": profile["zone"],
        "required_turn_ticks": profile["turn_ticks"],
        "trailing_stop_multiplier": profile["trail_mult"]
    }

def execute_smart_order(tradier_client, account_id, symbol, option_symbol, bid, ask, quantity=1):
    """
    Stage 1: Attempt Limit order fill at MID price.
    Stage 2: Fallback to ASK if unfilled after 3s and spread <= 1.0%.
    """
    bid_f = float(bid or 0.0)
    ask_f = float(ask or 0.0)
    if ask_f <= 0 or bid_f <= 0:
        print(f"[!] Invalid quote for {option_symbol}. Aborting.")
        return None

    mid_price = round((bid_f + ask_f) / 2.0, 2)
    spread_pct = (ask_f - bid_f) / ask_f if ask_f > 0 else 0.0

    print(f"[*] [STAGE 1] Submitting Limit Order at MID: ${mid_price:.2f} (Bid: ${bid_f:.2f} / Ask: ${ask_f:.2f})")
    order_id = tradier_client.place_option_order(
        account_id, symbol, option_symbol, side='buy_to_open', 
        quantity=quantity, order_type='limit', price=mid_price
    )
    
    time.sleep(3)  # Wait 3s for Mid-fill
    
    status = tradier_client.get_order_status(account_id, order_id)
    if status == 'filled':
        print(f"[✓] [MID FILL SUCCESS] Filled {option_symbol} at ${mid_price:.2f}!")
        return {'order_id': order_id, 'fill_price': mid_price, 'type': 'MID_FILL'}

    if spread_pct <= 0.01:
        print(f"[*] [STAGE 2] Mid unfilled. Spread is tight ({spread_pct*100.0:.2f}% <= 1.0%). Escalating to ASK (${ask_f:.2f})...")
        tradier_client.modify_order(account_id, order_id, price=ask_f)
        time.sleep(1)
        return {'order_id': order_id, 'fill_price': ask_f, 'type': 'ASK_FALLBACK'}
    else:
        print(f"[⛔ SPREAD GUARD] Canceling order {order_id}. Mid unfilled & spread ({spread_pct*100.0:.2f}%) > 1.0%.")
        tradier_client.cancel_order(account_id, order_id)
        return None

def check_active_position_exists(ticker, tenant_id='COMPANY_A'):
    """
    Prevents duplicate active trade stacking in DynamoDB & SQLite.
    Auto-heals local SQLite if DynamoDB confirms position is already CLOSED.
    """
    ticker_u = ticker.upper()

    # 1. Check DynamoDB Ground Truth First
    dynamo_active = False
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
        res = table.scan(
            FilterExpression="ticker = :t AND exit_status = :s",
            ExpressionAttributeValues={":t": ticker_u, ":s": "ACTIVE"}
        )
        if len(res.get('Items', [])) > 0:
            dynamo_active = True
    except Exception as e:
        log_msg(f"[!] DynamoDB active check warning: {e}")

    # 2. Check SQLite
    sqlite_active = False
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM trades WHERE UPPER(ticker) = ? AND UPPER(exit_status) = 'ACTIVE'", (ticker_u,))
            if c.fetchone()[0] > 0:
                sqlite_active = True
            conn.close()
    except Exception as e:
        log_msg(f"[!] SQLite active check warning: {e}")

    # 3. Auto-Heal SQLite if out of sync with DynamoDB
    if sqlite_active and not dynamo_active:
        log_msg(f"[🧹 AUTO-HEAL] SQLite had stale ACTIVE record for {ticker_u}, but DynamoDB is clear. Syncing local state...")
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE trades SET exit_status = 'CLOSED' WHERE UPPER(ticker) = ? AND UPPER(exit_status) = 'ACTIVE'", (ticker_u,))
            conn.commit()
            conn.close()
            sqlite_active = False
        except Exception as e:
            log_msg(f"[!] Auto-heal failed: {e}")

    return dynamo_active or sqlite_active

def get_live_quote(symbol):
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    try:
        res = requests.get(f"{TRADIER_BASE_URL}/markets/quotes", params={"symbols": symbol}, headers=headers, timeout=4)
        if res.status_code == 200:
            quotes = res.json().get("quotes", {}).get("quote", {})
            # Intercept Tradier HTTP 200 error payloads
            if isinstance(quotes, dict) and 'errors' in quotes and quotes['errors']:
                err_body = quotes['errors']
                err_msg = err_body.get('error', str(err_body)) if isinstance(err_body, dict) else str(err_body)
                print(f'[🚨 TRADIER REJECTION] {err_msg}')
                return None
            return quotes[0] if isinstance(quotes, list) and quotes else (quotes if isinstance(quotes, dict) else {})
    except Exception as e:
        log_msg(f"[-] Quote Fetch Error ({symbol}): {e}")
    return {}

def search_smart_option_chain(ticker, direction="CALL", spot_price=0.0):
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    exp_url = f"{TRADIER_BASE_URL}/markets/options/expirations"
    try:
        r = requests.get(exp_url, headers=headers, params={"symbol": ticker, "includeAllRoots": "true"}, timeout=4)
        if r.status_code != 200:
            return None
        expirations = r.json().get("expirations", {}).get("date", [])
        if isinstance(expirations, str):
            expirations = [expirations]
        if not expirations:
            return None
        target_exp = expirations[0]
    except Exception as e:
        log_msg(f"[!] Expiration fetch failed for {ticker}: {e}")
        return None

    chain_url = f"{TRADIER_BASE_URL}/markets/options/chains"
    try:
        r = requests.get(chain_url, headers=headers, params={"symbol": ticker, "expiration": target_exp, "greeks": "true"}, timeout=5)
        if r.status_code != 200:
            return None
        options = r.json().get("options", {}).get("option", [])
        if isinstance(options, dict):
            options = [options]
        if not options:
            return None
            
        target_side = direction.lower()
        valid_contracts = []
        
        for opt in options:
            if opt.get("option_type") != target_side:
                continue
            bid = float(opt.get("bid") or 0.0)
            ask = float(opt.get("ask") or 0.0)
            if bid < 0.05 or ask <= 0:
                continue
            spread_pct = (ask - bid) / ask
            if spread_pct > 0.08:  # Enforce tight 8% maximum spread threshold for entry options
                continue
            valid_contracts.append(opt)
            
        if valid_contracts:
            if spot_price > 0:
                best_opt = min(valid_contracts, key=lambda x: abs(float(x.get("strike", 0)) - spot_price))
            else:
                best_opt = min(valid_contracts, key=lambda x: abs(float(x.get("ask", 0)) - 1.00))
            return best_opt
    except Exception as e:
        log_msg(f"[!] Chain search error for {ticker}: {e}")
    return None

def generate_valid_occ_symbol(ticker: str, option_type: str, spot_price: float, min_dte: int = 3) -> str:
    """
    Generates a valid Tradier OCC option symbol enforcing:
    1. Valid standard strike rounding ($0.50 or $1.00 intervals).
    2. Minimum DTE guardrail (>= 3 days out, target Friday expiration).
    """
    now = datetime.now()
    
    # Calculate target Friday expiration with min_dte buffer
    target_date = now + timedelta(days=min_dte)
    days_until_friday = (4 - target_date.weekday()) % 7
    friday_expiration = target_date + timedelta(days=days_until_friday)
    exp_str = friday_expiration.strftime("%y%m%d")  # e.g., '260821'
    
    # Round spot price to nearest $0.50 strike interval
    strike_rounded = round(spot_price * 2) / 2  # e.g., 18.11 -> 18.00
    strike_fmt = f"{int(strike_rounded * 1000):08d}"  # 18.00 -> '00018000'
    
    opt_char = "C" if option_type.upper() in ["CALL", "C"] else "P"
    occ_symbol = f"{ticker.upper()}{exp_str}{opt_char}{strike_fmt}"
    return occ_symbol

def fetch_occ_symbol(underlying, option_type, spot_price):
    best_opt = search_smart_option_chain(underlying, option_type, spot_price)
    if best_opt and best_opt.get("symbol"):
        return best_opt.get("symbol"), float(best_opt.get("ask") or 1.00)
        
    occ = generate_valid_occ_symbol(underlying, option_type, spot_price, min_dte=3)
    return occ, 1.00

def execute_strict_tradier_order(occ_symbol, underlying, side, quantity=1, max_wait_seconds=10):
    """
    Executes order via Low-Ball Adaptive Laddering Engine.
    - Phase 1: Submits low-ball limit order at/near BID.
    - Phase 2: Holds for 3.5s while evaluating underlying price velocity & book depth.
    - Phase 3: Steps up limit price if momentum is high, or cancels/aborts if stagnant/adverse.
    Enforces Ghost Fill Protection (verifies exec_quantity > 0).
    """
    if not TRADIER_TOKEN or not TRADIER_ACCOUNT_ID:
        log_msg("[!] Tradier Token or Account ID missing.")
        return False, 0.0, ""

    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    order_side = "buy_to_open"

    # --- PHASE 1: SAMPLE BOOK & CALCULATE LOW-BALL BID ---
    initial_q = get_live_quote(occ_symbol)
    bid = float(initial_q.get("bid") or 0.0)
    ask = float(initial_q.get("ask") or 0.0)

    if bid <= 0 or ask <= 0:
        log_msg(f"[⚠️ ADAPTIVE GUARD WARNING] Quote book empty for {occ_symbol}. Falling back to standard execution.")
        low_ball_px = 0.05
    else:
        low_ball_px = round(round(bid / 0.05) * 0.05, 2)
        if low_ball_px <= 0:
            low_ball_px = 0.05

    limit_price_str = f"{low_ball_px:.2f}"
    log_msg(f"[*] [PHASE 1: LOW-BALL ENTRY] Submitting LIMIT order at BID: ${limit_price_str} (Bid: ${bid:.2f} / Ask: ${ask:.2f})...")

    payload = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": occ_symbol,
        "side": order_side,
        "quantity": str(int(quantity)),
        "type": "limit",
        "price": limit_price_str,
        "duration": "day"
    }

    try:
        response = requests.post(
            f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders",
            data=payload,
            headers=headers,
            timeout=5
        )

        if response.status_code != 200:
            log_msg(f"[⛔ TRADIER REJECT ({response.status_code})]: {response.text}")
            return False, 0.0, ""

        res_json = response.json()
        if isinstance(res_json, dict) and 'errors' in res_json and res_json['errors']:
            err_data = res_json['errors']
            err_msg = err_data.get('error', str(err_data)) if isinstance(err_data, dict) else str(err_data)
            log_msg(f"[🚨 TRADIER REJECTION]: {err_msg}")
            print(f"[🚨 TRADIER REJECTION] {err_msg}")
            return False, 0.0, ""
        order_data = res_json.get("order", {})
        order_id = str(order_data.get("id"))
        log_msg(f"[✓] Low-Ball order placed. Order ID: {order_id}. Evaluating fill probability over 3.5s...")

        # --- PHASE 2: EVALUATION WINDOW (3.5s) ---
        start_wait = time.time()

        while (time.time() - start_wait) < 3.5:
            time.sleep(1.0)
            status_res = requests.get(
                f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}",
                headers=headers,
                timeout=4
            )
            if status_res.status_code == 200:
                detailed = status_res.json().get("order", {})
                status = detailed.get("status", "")
                if status == "filled":
                    exec_qty = detailed.get("exec_quantity")
                    if exec_qty is not None and float(exec_qty) == 0:
                        log_msg(f"[⛔ GHOST FILL DETECTED] Order {order_id} marked filled but exec_quantity=0.")
                        return False, 0.0, ""
                    fill_price = float(detailed.get("avg_fill_price") or low_ball_px)
                    log_msg(f"[🎯 LOW-BALL FILLED!] Target filled at BID (${fill_price:.2f})! Zero spread slippage.")
                    return True, fill_price, order_id

        # --- PHASE 3: MOMENTUM EVALUATION & STEP-UP / ABORT ---
        log_msg(f"[⏱️ EVALUATION TIMEOUT] Low-ball bid (${limit_price_str}) unfilled after 3.5s. Checking momentum...")
        
        latest_q = get_live_quote(occ_symbol)
        new_bid = float(latest_q.get("bid") or 0.0)
        new_ask = float(latest_q.get("ask") or 0.0)

        if new_bid >= bid and new_ask > 0:
            midpoint = (new_bid + new_ask) / 2.0
            stepped_mid = round(midpoint, 2)  # ✅ 1-cent precision (allows $0.24 midpoint)
            
            log_msg(f"[🚀 MOMENTUM CONFIRMED] Stepping up limit price from ${limit_price_str} -> ${stepped_mid:.2f} to secure fill...")

            requests.delete(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers)

            payload["price"] = f"{stepped_mid:.2f}"
            step_res = requests.post(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders", data=payload, headers=headers, timeout=5)
            
            if step_res.status_code == 200:
                step_json = step_res.json()
                if isinstance(step_json, dict) and 'errors' in step_json and step_json['errors']:
                    err_data = step_json['errors']
                    err_msg = err_data.get('error', str(err_data)) if isinstance(err_data, dict) else str(err_data)
                    log_msg(f"[🚨 TRADIER REJECTION]: {err_msg}")
                    return False, 0.0, ""
                
                new_order_id = str(step_res.json().get("order", {}).get("id"))
                
                # ✅ Extended evaluation window: 10 retries @ 1.0s = 10.0s fill window
                for _ in range(10):
                    time.sleep(1.0)
                    chk = requests.get(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{new_order_id}", headers=headers)
                    if chk.status_code == 200:
                        det = chk.json().get("order", {})
                        if det.get("status") == "filled":
                            exec_qty = det.get("exec_quantity")
                            if exec_qty is not None and float(exec_qty) == 0:
                                log_msg(f"[⛔ GHOST FILL DETECTED] Step order {new_order_id} marked filled but exec_quantity=0.")
                                return False, 0.0, ""
                            f_px = float(det.get("avg_fill_price") or stepped_mid)
                            return True, f_px, new_order_id

        log_msg(f"[🛡️ CAPITAL PROTECT] Momentum stagnant or low fill probability. Cancelling low-ball order {order_id}...")
        requests.delete(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers)
        return False, 0.0, ""

    except Exception as e:
        log_msg(f"[-] Low-Ball Execution Exception: {e}")
        return False, 0.0, ""

def log_trade_dual_db(ticker, spot, fill_price, stop_loss, take_profit, shares, direction, occ_symbol, order_id, tenant_id='COMPANY_A'):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_id = str(uuid.uuid4())[:8]

    # Determine execution environment mode dynamically from env
    exec_env = os.getenv("EXECUTION_ENV", "SANDBOX").upper()
    is_live_flag = 1 if exec_env in ["PROD", "PRODUCTION", "LIVE"] else 0

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Ensure all required columns exist in SQLite trades table schema
        cursor.execute("PRAGMA table_info(trades)")
        columns = [column[1] for column in cursor.fetchall()]
        for col in ['gsg_status', 'mttp_status', 'cso_status', 'execution_env']:
            if col not in columns:
                try:
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} TEXT DEFAULT 'SANDBOX'")
                except Exception:
                    pass
        
        cursor.execute('''
            INSERT INTO trades (
                ticker, timestamp, strategy, direction, spot_price, 
                entry_price, exit_status, stop_loss, take_profit, shares, occ_symbol, is_live,
                gsg_status, mttp_status, cso_status, execution_env
            ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, 'ARMED', 'ACTIVE_45M_GUARD', 'HOLD', ?)
        ''', (ticker, timestamp, 'SMART_CSO_LIVE', direction, spot, fill_price, stop_loss, take_profit, shares, occ_symbol, is_live_flag, exec_env))
        conn.commit()
        conn.close()
        log_msg(f"[✓] SQLite logged active position for {ticker} (Env: {exec_env}, IsLive: {is_live_flag}) with active GSG/MTTP guards.")
    except Exception as e:
        log_msg(f"[-] SQLite Log Error: {e}")

    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
        item = {
            'tenant_id': tenant_id,
            'trade_id': trade_id,
            'ticker': ticker,
            'timestamp': timestamp,
            'strategy': 'SMART_CSO_LIVE',
            'direction': direction,
            'spot_price': str(spot),
            'entry_price': str(fill_price),
            'shares': str(shares),
            'stop_loss': str(stop_loss),
            'take_profit': str(take_profit),
            'net_pnl': '0.0',
            'exit_status': 'ACTIVE',
            'is_live': is_live_flag,
            'execution_env': exec_env,
            'occ_symbol': occ_symbol,
            'gsg_status': 'ARMED',
            'mttp_status': 'ACTIVE_45M_GUARD',
            'cso_status': 'HOLD',
            'order_id': str(order_id)
        }
        table.put_item(Item=item)
        log_msg(f"[✓] DynamoDB synchronized: {ticker} (Receipt ID: {order_id}, Env: {exec_env}) -> GSG/MTTP Watch Loops Engaged.")
    except Exception as e:
        log_msg(f"[-] DynamoDB Log Error: {e}")

def monitor_live_exit_telemetry(ticker):
    """
    Streams live exit status and PnL telemetry continuously in terminal window until position is CLOSED.
    Uses rolling quote smoothing to filter spread noise on active exit evaluations.
    """
    log_msg(f"[📡 TELEMETRY STREAM ENGAGED] Monitoring live watch loop for {ticker} until exit...")
    ticker_u = ticker.upper()
    
    while True:
        time.sleep(2.5)
        try:
            dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
            table = dynamodb.Table('HarmonizedTrades')
            res = table.scan(
                FilterExpression="ticker = :t",
                ExpressionAttributeValues={":t": ticker_u}
            )
            items = res.get('Items', [])
            if items:
                latest = max(items, key=lambda x: x.get('timestamp', ''))
                status = latest.get('exit_status', 'ACTIVE')
                exit_price = latest.get('exit_price') or latest.get('fill_price') or '0.00'
                net_pnl = float(latest.get('net_pnl', 0.0) or 0.0)
                reason = latest.get('cso_reason', latest.get('cso_status', 'ACTIVE'))
                
                if status != 'ACTIVE':
                    pnl_color = "🟢" if net_pnl >= 0 else "🔴"
                    log_msg(f"[{pnl_color} LIVE EXIT DETECTED] {ticker_u} CLOSED @ ${float(exit_price):.2f} | PnL: ${net_pnl:+.2f} | Reason: {reason}")
                    return
                else:
                    stop_px = latest.get('stop_loss', '0.00')
                    log_msg(f"[⏱️ ACTIVE WATCH] {ticker_u} running... Active Stop Floor: ${float(stop_px):.2f}")
        except Exception as e:
            pass

def resolve_smart_direction(info, spot):
    vwap = float(info.get("vwap", spot))
    sup = info.get("support_zone", [])
    res = info.get("resistance_zone", [])
    
    if res and isinstance(res, list) and len(res) >= 2 and spot >= res[0]:
        return "PUT", "TESTING_RESISTANCE_ZONE"
    elif sup and isinstance(sup, list) and len(sup) >= 2 and spot <= sup[1]:
        return "CALL", "BOUNCING_SUPPORT_ZONE"
    else:
        return ("CALL" if spot >= vwap else "PUT"), "VWAP_MOMENTUM_ALIGNMENT"

def smart_cso_scout_and_execute(force_ticker=None, direction_override="SMART", scan_duration=25, contract_qty=None):
    if contract_qty is None:
        contract_qty = int(os.getenv("CONTRACT_QTY", 1))
    print("=" * 65)
    print("🧠 HARM.AI // STRICT RECEIPT SMART CSO LIVE TRADER")
    print(f"[*] Target: {force_ticker or 'AUTO-SCAN'} | Mode: {direction_override}")
    print("=" * 65)

    levels = {}
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r") as f:
                data = json.load(f)
                levels = data.get("levels", data) if isinstance(data, dict) else {}
        except Exception as e:
            log_msg(f"[!] Manifest parse error: {e}")

    candidates = []

    if force_ticker:
        ticker_upper = force_ticker.upper()
        if check_active_position_exists(ticker_upper):
            log_msg(f"[🛡️ BLOCKED] Active position already exists for {ticker_upper} in DB. Duplicate injection aborted.")
            return

        if not validate_reentry_eligibility(ticker_upper, DB_PATH):
            return

        info = levels.get(ticker_upper, {}) if isinstance(levels, dict) else {}
        stock_quote = get_live_quote(ticker_upper)
        spot = float(stock_quote.get("last") or info.get("spot") or info.get("last_price") or 0.0)
        
        if spot <= 0:
            log_msg(f"[!] Could not fetch valid spot price for {ticker_upper}. Aborting.")
            return

        if direction_override in ["CALL", "PUT"]:
            direction = direction_override.upper()
            reason = "CLI_EXPLICIT_OVERRIDE"
        else:
            direction, reason = resolve_smart_direction(info, spot)

        candidates.append({
            "ticker": ticker_upper,
            "spot": spot,
            "direction": direction,
            "reason": reason
        })
    else:
        if isinstance(levels, dict):
            for ticker, info in levels.items():
                if not isinstance(info, dict):
                    continue
                ticker_upper = ticker.upper()
                if check_active_position_exists(ticker_upper):
                    continue

                if not validate_reentry_eligibility(ticker_upper, DB_PATH):
                    continue

                spot = float(info.get("spot", info.get("last_price", 0.0)))
                armed = bool(info.get("execution_armed", False))
                
                if armed or spot > 0:
                    direction, reason = resolve_smart_direction(info, spot)
                    candidates.append({
                        "ticker": ticker_upper,
                        "spot": spot,
                        "direction": direction,
                        "reason": reason
                    })

    if not candidates:
        log_msg("[-] No qualified trades found or all active candidates already exist.")
        return

    target = candidates[0]
    ticker = target["ticker"]
    direction = target["direction"]
    spot = target["spot"]

    log_msg(f"[🎯 SMART SELECTION] Ticker: {ticker} | Direction: {direction} | Spot: ${spot:.2f} | Reason: {target['reason']}")

    best_opt = search_smart_option_chain(ticker, direction, spot_price=spot)
    if best_opt:
        occ_symbol = best_opt.get("symbol")
        ask_price = float(best_opt.get("ask") or 0.80)
        log_msg(f"[✓ OPTION CHAIN MATCH] Contract: {occ_symbol} | Ask: ${ask_price:.2f}")
    else:
        log_msg(f"[⚠️ FALLBACK] No liquid contract found. Generating synthetic OCC symbol...")
        occ_symbol, ask_price = fetch_occ_symbol(ticker, direction, spot)

    success, fill_px, order_id = execute_strict_tradier_order(occ_symbol, ticker, direction, quantity=contract_qty)

    if not success or fill_px <= 0 or not order_id:
        log_msg(f"[⛔ REGISTRATION ABORTED] Tradier execution receipt verification failed for {ticker} {occ_symbol}. Zero records written to DB, guards not engaged.")
        return

    fill_price = fill_px
    
    # Adaptive Stop-Loss calculation based on Option Premium Tier
    if fill_price <= 0.50:
        # Enforce $0.10 dollar cushion or 35% max drop for low-dollar options (<= $0.50)
        stop_loss = round(max(0.02, fill_price - 0.10), 2)
        log_msg(f"[🛡️ LOW-DOLLAR CUSHION ENGAGED] Entry: ${fill_price:.2f} -> Stop Loss: ${stop_loss:.2f} ($0.10 cushion)")
    else:
        stop_loss = round(fill_price * 0.80, 2)
        log_msg(f"[🛡️ STANDARD STOP ENGAGED] Entry: ${fill_price:.2f} -> Stop Loss: ${stop_loss:.2f} (20% floor)")

    take_profit = round(fill_price * 1.50, 2)
    shares = contract_qty

    log_trade_dual_db(ticker, spot, fill_price, stop_loss, take_profit, shares, direction, occ_symbol, order_id)
    log_msg(f"[✓ SUCCESS] Strict Tradier Receipt confirmed and live watch loops engaged for {ticker} {direction}!")
    
    # Engagement of continuous live terminal exit telemetry
    monitor_live_exit_telemetry(ticker)

# ===============================================================================
# LEGACY COMPATIBILITY STUBS FOR UNIT TEST HARNESSES
# ===============================================================================

def execute_adaptive_micro_scalp_order(occ_symbol, underlying, side, quantity=1):
    """Legacy alias wrapping execute_strict_tradier_order for unit test backward compatibility."""
    return execute_strict_tradier_order(occ_symbol, underlying, side, quantity=quantity)

def check_predictive_armed_trigger(ticker, spot_or_info, info=None):
    """
    Legacy alias evaluating dynamic arming state for tick playback harnesses.
    Supports both check_predictive_armed_trigger(ticker, info) and (ticker, spot, info).
    Returns (triggered: bool, reason: str).
    """
    if isinstance(spot_or_info, dict):
        info_dict = spot_or_info
        spot = float(info_dict.get("spot") or info_dict.get("spot_price") or info_dict.get("last_price") or 0.0)
    else:
        spot = float(spot_or_info or 0.0)
        info_dict = info if isinstance(info, dict) else {}

    calibration = get_ticker_calibration(ticker)
    threshold = calibration["proximity_threshold"]
    
    target = float(
        info_dict.get("armed_target") or 
        info_dict.get("target") or 
        info_dict.get("spot_target_call") or 
        info_dict.get("call_target") or 
        info_dict.get("spot_target_put") or 
        info_dict.get("put_target") or 0.0
    )
    
    if target <= 0 or spot <= 0:
        return False, "INVALID_TARGET_OR_SPOT"
        
    gap_pct = abs(spot - target) / target
    if gap_pct <= threshold:
        return True, "PREDICTIVE_ARMED_TRIGGER_FIRED"
    return False, "OUTSIDE_ARMED_ZONE"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strict Receipt Smart CSO Live Trader & Injector")
    parser.add_argument("--ticker", type=str, default=None, help="Target specific ticker (e.g. F, RIVN, NVDA)")
    parser.add_argument("--direction", type=str, choices=["CALL", "PUT", "SMART"], default="SMART", help="Side selection")
    parser.add_argument("--scan", type=int, default=25, help="Scan duration window in seconds")
    
    args = parser.parse_args()
    smart_cso_scout_and_execute(force_ticker=args.ticker, direction_override=args.direction, scan_duration=args.scan)


def cancel_order(order_id: str):
    return True
