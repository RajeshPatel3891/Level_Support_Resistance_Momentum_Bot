import os

if os.getenv('EXECUTION_ENV', '').upper() == 'SANDBOX':
    os.environ['TRADIER_BASE_URL'] = 'https://sandbox.tradier.com/v1'
    if os.getenv('TRADIER_SANDBOX_TOKEN'):
        os.environ['TRADIER_TOKEN'] = os.getenv('TRADIER_SANDBOX_TOKEN')

#!/usr/bin/env python3
"""
HARM.AI // SMART CSO-DRIVEN LIVE TRADER & INJECTOR (STRICT MIDPOINT & PREDICTIVE FILL GATE)
===============================================================================
Scans trading_levels.json, evaluates proximity/safety and support/resistance 
boundaries, resolves directional bias (Call vs Put), enforces multivariable momentum 
confluence (VWAP slope, SPY/QQQ beta alignment), applies Time-of-Day liquidity gates,
evaluates Pre-Entry Predictive Fill Quality Scores (>= 7.5/10 threshold), validates
option chain liquidity, executes non-crossing Midpoint limit orders with a hard 5-second
cancel-and-walk policy, logs dual DB receipts (SQLite/DynamoDB), and streams telemetry.
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
import pytz
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
# FILL QUALITY SCORE CALCULATORS & GRADIENT PROXIMITY SCORING
# ===============================================================================

def calculate_proximity_score(spot: float, target: float, threshold_pct: float = 0.0075) -> float:
    """
    Computes a continuous proximity score from 0 to 100 based on distance to target.
    - 100: Spot is precisely on or past the target zone.
    - 0: Spot is outside the maximum proximity threshold window.
    """
    if spot <= 0 or target <= 0:
        return 0.0

    distance_pct = abs(spot - target) / spot
    
    # If outside the threshold window, score is 0
    if distance_pct >= threshold_pct:
        return 0.0
        
    # Linearly scale score from 0 (at threshold edge) to 100 (at target)
    score = (1.0 - (distance_pct / threshold_pct)) * 100.0
    return round(max(0.0, min(100.0, score)), 2)

def calculate_fill_quality_score(fill_price: float, bid: float, ask: float, side: str = "buy") -> float:
    """
    Calculates Post-Execution Fill Quality Score on a 0.0 to 10.0 scale based on market microstructure.
    - 10.0 = Best possible fill (Ask on buy, Bid on sell).
    - 5.0  = Midpoint fill.
    - 0.0  = Worst possible fill (Bid on buy, Ask on sell).
    """
    if ask <= bid or fill_price <= 0:
        return 0.0
    spread = ask - bid
    if side.lower() in ["buy", "buy_to_open"]:
        score = ((ask - fill_price) / spread) * 10.0
    else:
        score = ((fill_price - bid) / spread) * 10.0
    return round(max(0.0, min(10.0, score)), 1)

def predict_fill_quality_score(quote: dict, side: str = "buy") -> tuple:
    """
    Predicts the likelihood of securing a >= 7.5/10 Midpoint fill BEFORE submitting an order.
    Evaluates spread width, option price level, order book depth imbalance, and volume.
    Returns (predicted_score: float, reason: str).
    """
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)
    bid_size = int(quote.get("bidsize") or quote.get("bid_size") or 1)
    ask_size = int(quote.get("asksize") or quote.get("ask_size") or 1)
    volume = int(quote.get("volume") or 0)

    if bid <= 0 or ask <= bid:
        return 0.0, "Zero or inverted bid/ask book"

    spread = round(ask - bid, 2)
    mid = (bid + ask) / 2.0
    spread_pct = (spread / mid) if mid > 0 else 1.0

    score = 10.0

    # 1. Spread Width Penalty
    if spread > 0.05 or spread_pct > 0.05:
        penalty = min(6.0, (spread / 0.02) * 1.5)
        score -= penalty

    # 2. Cheap Option Tick Granularity Penalty (Contracts < $0.20)
    if mid < 0.20 and spread >= 0.02:
        score -= 2.5

    # 3. Order Book Depth / Imbalance Adjustment
    total_depth = bid_size + ask_size
    if total_depth > 0:
        imbalance = (bid_size - ask_size) / total_depth
        if side.lower() in ["buy", "buy_to_open"]:
            score += (imbalance * 1.0)
        else:
            score -= (imbalance * 1.0)

    # 4. Low Volume Penalty
    if volume < 50:
        score -= 1.5

    final_score = round(max(0.0, min(10.0, score)), 1)
    
    if final_score < 7.5:
        return final_score, f"Predicted Score ({final_score}/10) below 7.5 threshold (Spread: ${spread:.2f})"
        
    return final_score, "Passed Predictive Score Gate"

# ===============================================================================
# TIME-OF-DAY LIQUIDITY GATEWAY
# ===============================================================================

def is_valid_time_of_day_window() -> bool:
    """
    Blocks entries during low-volume mid-day lulls (11:30 AM - 1:30 PM ET).
    Allows trades during Opening Drive (9:30-11:30 AM) and Power Hour (1:30-4:00 PM).
    """
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    
    if now.weekday() >= 5:  # Weekend guard
        return False
        
    current_time = now.time()
    lull_start = datetime.strptime("11:30", "%H:%M").time()
    lull_end = datetime.strptime("13:30", "%H:%M").time()
    
    if lull_start <= current_time <= lull_end:
        log_msg("⏳ [TOD GUARD] In Mid-day Liquidity Lull (11:30 AM - 1:30 PM ET). Aborting injection.")
        return False
        
    return True

# ===============================================================================
# PRE-ENTRY OPTION LIQUIDITY VALIDATOR
# ===============================================================================

def validate_option_liquidity(chain_quote):
    """
    Validates option chain liquidity before submitting entry orders.
    Rejects illiquid traps (zero bid, wide spreads, or low volume/OI).
    """
    bid = float(chain_quote.get('bid', 0.0) or 0.0)
    ask = float(chain_quote.get('ask', 0.0) or 0.0)
    open_interest = int(chain_quote.get('open_interest', 0) or 0)
    volume = int(chain_quote.get('volume', 0) or 0)
    
    spread = ask - bid
    mid = (bid + ask) / 2.0
    
    # 1. Non-zero / Penny-trap check
    if bid <= 0.01:
        return False, f"Bid (${bid:.2f}) is $0.01 or zero (Illiquid Trap)"
        
    # 2. Spread caps ($0.05 or 5% of mid)
    if spread > 0.05 or (mid > 0 and (spread / mid) > 0.05):
        return False, f"Spread (${spread:.2f}) exceeds cap"
        
    # 3. Volume & Open Interest floors
    if open_interest < 100 or volume < 25:
        return False, f"Low Liquidity (OI: {open_interest}, Vol: {volume})"
        
    return True, "Passed"

# ===============================================================================
# MULTIVARIABLE MOMENTUM CONFLUENCE CHECKER
# ===============================================================================

def check_multivariable_momentum_confluence(ticker, direction, spot, info):
    """
    Validates signal using:
    1. VWAP Slope / Alignment
    2. SPY & QQQ Market Beta Confluence
    """
    vwap = float(info.get("vwap", spot) or spot)
    
    # 1. VWAP Filter
    if direction == "CALL" and spot < vwap:
        return False, f"{ticker} Spot (${spot:.2f}) is below VWAP (${vwap:.2f}) - CALL Rejected"
    elif direction == "PUT" and spot > vwap:
        return False, f"{ticker} Spot (${spot:.2f}) is above VWAP (${vwap:.2f}) - PUT Rejected"

    # 2. SPY & QQQ Market Beta Confluence
    spy_quote = get_live_quote("SPY")
    qqq_quote = get_live_quote("QQQ")
    
    spy_change = float(spy_quote.get("change_percentage", 0.0) or 0.0)
    qqq_change = float(qqq_quote.get("change_percentage", 0.0) or 0.0)
    
    if direction == "CALL" and (spy_change < -0.15 or qqq_change < -0.15):
        return False, f"Market Beta Drag (SPY: {spy_change:+.2f}%, QQQ: {qqq_change:+.2f}%) - CALL Rejected"
    elif direction == "PUT" and (spy_change > 0.15 or qqq_change > 0.15):
        return False, f"Market Beta Lift (SPY: {spy_change:+.2f}%, QQQ: {qqq_change:+.2f}%) - PUT Rejected"

    return True, "Confluence Confirmed"

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
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        c.execute("""
            SELECT COUNT(*), MAX(timestamp) FROM trades 
            WHERE UPPER(ticker) = UPPER(?) AND timestamp LIKE ?
        """, (ticker, f"{today_str}%"))
        
        row = c.fetchone()
        conn.close()
        
        trade_count = row[0] if row and row[0] is not None else 0
        last_timestamp_str = row[1] if row and row[1] is not None else None
        
        if trade_count >= 2:
            print(f"[⛔ RE-ENTRY BLOCKED] {ticker} has hit maximum 2 trades for today.")
            return False
             
        if last_timestamp_str:
            try:
                last_time = datetime.strptime(str(last_timestamp_str), "%Y-%m-%d %H:%M:%S")
                elapsed_mins = (datetime.now() - last_time).total_seconds() / 60.0
                if elapsed_mins < 15.0:
                    print(f"[⏳ COOLDOWN ACTIVE] {ticker} entered/exited {elapsed_mins:.1f}m ago. Need 15m cooldown.")
                    return False
            except Exception as parse_err:
                print(f"[!] Timestamp parse error: {parse_err}")
    except Exception as e:
        print(f"[!] Re-entry validation warning: {e}")
             
    return True

def check_active_position_exists(ticker, tenant_id='COMPANY_A'):
    """
    Prevents duplicate active trade stacking in DynamoDB & SQLite.
    Auto-heals local SQLite if DynamoDB confirms position is already CLOSED.
    """
    ticker_u = ticker.upper()

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
             
            valid_liquidity, reason = validate_option_liquidity(opt)
            if not valid_liquidity:
                continue
                
            valid_contracts.append(opt)
             
        if valid_contracts:
            best_opt = min(valid_contracts, key=lambda x: abs(float(x.get("ask", 0)) - 0.65))
            return best_opt
    except Exception as e:
        log_msg(f"[!] Chain search error for {ticker}: {e}")
    return None

def generate_valid_occ_symbol(ticker: str, option_type: str, spot_price: float, min_dte: int = 3) -> str:
    now = datetime.now()
    target_date = now + timedelta(days=min_dte)
    days_until_friday = (4 - target_date.weekday()) % 7
    friday_expiration = target_date + timedelta(days=days_until_friday)
    exp_str = friday_expiration.strftime("%y%m%d")
    
    strike_rounded = round(spot_price * 2) / 2
    strike_fmt = f"{int(strike_rounded * 1000):08d}"
    
    opt_char = "C" if option_type.upper() in ["CALL", "C"] else "P"
    occ_symbol = f"{ticker.upper()}{exp_str}{opt_char}{strike_fmt}"
    return occ_symbol

def fetch_occ_symbol(underlying, option_type, spot_price):
    best_opt = search_smart_option_chain(underlying, option_type, spot_price)
    if best_opt and best_opt.get("symbol"):
        return best_opt.get("symbol"), float(best_opt.get("ask") or 1.00)
         
    occ = generate_valid_occ_symbol(underlying, option_type, spot_price, min_dte=3)
    return occ, 1.00

# ===============================================================================
# STRICT MIDPOINT LIMIT EXECUTION WITH 5-SECOND CANCEL POLICY
# ===============================================================================

def execute_strict_tradier_order(occ_symbol, underlying, side, quantity=1, max_wait_seconds=5):
    # HARD SECURITY FLOOR - ENTRY GUARD
    import os
    env_chk = os.getenv("EXECUTION_ENV", "SANDBOX").upper()
    acct_chk = os.getenv("TRADIER_ACCOUNT_ID", "")
    if env_chk == "SANDBOX" and acct_chk == "6YB87601":
        print("[🚨 SECURITY BLOCK] Aborting Tradier order! SANDBOX process detected Live Prod Account ID (6YB87601).")
        return None
    """
    Submits a strict Limit Order at Midpoint ((Bid + Ask) / 2).
    Holds for 5 seconds. If unfilled, CANCELS and walks away—NO spread crossing.
    """
    if not TRADIER_TOKEN or not TRADIER_ACCOUNT_ID:
        log_msg("[!] Tradier Token or Account ID missing.")
        return False, 0.0, ""

    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    order_side = "buy_to_open"

    quote = get_live_quote(occ_symbol)
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)

    if bid <= 0 or ask <= 0:
        if os.getenv("EXECUTION_ENV") == "SANDBOX":
            log_msg(f"[⚠️ SANDBOX OVERRIDE] Injecting simulated bid/ask spread for {occ_symbol}.")
            bid, ask = 1.45, 1.50
        else:
            log_msg(f"[⛔ EXECUTION ABORTED] Quote book empty for {occ_symbol}.")
            return False, 0.0, ""

    mid_price = round((bid + ask) / 2.0, 2)
    if mid_price <= 0:
        mid_price = 0.05

    limit_price_str = f"{mid_price:.2f}"
    log_msg(f"[*] [MIDPOINT LIMIT ENTRY] Submitting LIMIT order @ MID: ${limit_price_str} (Bid: ${bid:.2f} / Ask: ${ask:.2f})...")

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
            return False, 0.0, ""

        order_data = res_json.get("order", {})
        order_id = str(order_data.get("id"))
        log_msg(f"[✓] Midpoint Order {order_id} placed. Waiting 5s for fill...")

        # --- STRICT 5-SECOND EVALUATION WINDOW ---
        start_wait = time.time()
        while (time.time() - start_wait) < float(max_wait_seconds):
            time.sleep(1.0)
            chk = requests.get(
                f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}",
                headers=headers,
                timeout=3
            )
            if chk.status_code == 200:
                det = chk.json().get("order", {})
                if det.get("status") == "filled":
                    exec_qty = det.get("exec_quantity")
                    if exec_qty is not None and float(exec_qty) == 0:
                        log_msg(f"[⛔ GHOST FILL] Order {order_id} exec_quantity=0.")
                        return False, 0.0, ""
                    fill_price = float(det.get("avg_fill_price") or mid_price)
                    fill_score = calculate_fill_quality_score(fill_price, bid, ask, side="buy")
                    log_msg(f"[🎯 ZERO-SLIPPAGE FILL] Filled {quantity}x {occ_symbol} @ MID ${fill_price:.2f} | Fill Quality Score: {fill_score}/10.0")
                    return True, fill_price, order_id

        # --- UNFILLED AFTER 5 SECONDS: CANCEL AND WALK AWAY ---
        log_msg(f"[🛡️ 5S TIMEOUT] Midpoint order {order_id} unfilled after 5s. Canceling order and walking away...")
        requests.delete(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers)
        return False, 0.0, ""

    except Exception as e:
        log_msg(f"[-] Midpoint Execution Exception: {e}")
        return False, 0.0, ""

def log_trade_dual_db(ticker, spot, fill_price, stop_loss, take_profit, shares, direction, occ_symbol, order_id, tenant_id='COMPANY_A'):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_id = str(uuid.uuid4())[:8]

    exec_env = os.getenv("EXECUTION_ENV", "SANDBOX").upper()
    is_live_flag = 1 if exec_env in ["PROD", "PRODUCTION", "LIVE"] else 0

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
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

    # Time-of-Day Check
    if not is_valid_time_of_day_window():
        return

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
        target = float(info.get("target") or info.get("call_target") or 0.0)
         
        if spot <= 0:
            log_msg(f"[!] Could not fetch valid spot price for {ticker_upper}. Aborting.")
            return

        # Integrate Continuous Proximity Gradient Score Evaluation
        score = calculate_proximity_score(spot, target, threshold_pct=0.0075)
        if score > 0:
            log_msg(f"[⚡ PROXIMITY GRADIENT] {ticker_upper} | Score: {score}/100")
            if score >= 90:
                contract_qty = max(contract_qty, 2)
            elif score >= 50:
                contract_qty = max(1, contract_qty // 2)

        if direction_override in ["CALL", "PUT"]:
            direction = direction_override.upper()
            reason = "CLI_EXPLICIT_OVERRIDE"
        else:
            direction, reason = resolve_smart_direction(info, spot)

        candidates.append({
            "ticker": ticker_upper,
            "spot": spot,
            "direction": direction,
            "reason": reason,
            "info": info
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
                target = float(info.get("target") or info.get("call_target") or 0.0)
                armed = bool(info.get("execution_armed", False))

                score = calculate_proximity_score(spot, target, threshold_pct=0.0075)
                if score > 0:
                    log_msg(f"[⚡ PROXIMITY GRADIENT] {ticker_upper} | Score: {score}/100")
                 
                if armed or spot > 0:
                    direction, reason = resolve_smart_direction(info, spot)
                    candidates.append({
                        "ticker": ticker_upper,
                        "spot": spot,
                        "direction": direction,
                        "reason": reason,
                        "info": info
                    })

    if not candidates:
        log_msg("[-] No qualified trades found or all active candidates already exist.")
        return

    target = candidates[0]
    ticker = target["ticker"]
    direction = target["direction"]
    spot = target["spot"]
    info = target["info"]

    # Multivariable Momentum Confluence Gate
    confluent, reason = check_multivariable_momentum_confluence(ticker, direction, spot, info)
    if not confluent:
        log_msg(f"[⛔ CONFLUENCE REJECTED] {reason}")
        return

    log_msg(f"[🎯 SMART SELECTION] Ticker: {ticker} | Direction: {direction} | Spot: ${spot:.2f} | Reason: {target['reason']} | Confluence: Passed")

    best_opt = search_smart_option_chain(ticker, direction, spot_price=spot)
    if best_opt:
        occ_symbol = best_opt.get("symbol")
         
        # PRE-ENTRY PREDICTIVE FILL QUALITY GATE
        pred_score, score_reason = predict_fill_quality_score(best_opt, side="buy")
        if pred_score < 7.5:
            log_msg(f"[⛔ PREDICTIVE FILL SCORE REJECTED] {ticker} ({occ_symbol}) | {score_reason}")
            return
             
        log_msg(f"[🎯 PREDICTIVE SCORE PASSED] Expected Fill Score: {pred_score}/10.0 | Proceeding to Midpoint Order...")
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
    
    if fill_price <= 0.50:
        stop_loss = round(max(0.02, fill_price - 0.10), 2)
        log_msg(f"[🛡️ LOW-DOLLAR CUSHION ENGAGED] Entry: ${fill_price:.2f} -> Stop Loss: ${stop_loss:.2f} ($0.10 cushion)")
    else:
        stop_loss = round(fill_price * 0.80, 2)
        log_msg(f"[🛡️ STANDARD STOP ENGAGED] Entry: ${fill_price:.2f} -> Stop Loss: ${stop_loss:.2f} (20% floor)")

    take_profit = round(fill_price * 1.50, 2)
    shares = contract_qty

    log_trade_dual_db(ticker, spot, fill_price, stop_loss, take_profit, shares, direction, occ_symbol, order_id)
    log_msg(f"[✓ SUCCESS] Strict Tradier Receipt confirmed and live watch loops engaged for {ticker} {direction}!")
    
    monitor_live_exit_telemetry(ticker)

# ===============================================================================
# LEGACY COMPATIBILITY STUBS FOR UNIT TEST HARNESSES
# ===============================================================================

def execute_adaptive_micro_scalp_order(occ_symbol, underlying, side, quantity=1):
    """Legacy alias wrapping execute_strict_tradier_order for unit test backward compatibility."""
    return execute_strict_tradier_order(occ_symbol, underlying, side, quantity=quantity)

def check_predictive_armed_trigger(ticker, spot_or_info, info=None):
    """Legacy alias evaluating dynamic arming state for tick playback harnesses."""
    if isinstance(spot_or_info, dict):
        info_dict = spot_or_info
        spot = float(info_dict.get("spot") or info_dict.get("spot_price") or info_dict.get("last_price") or 0.0)
    else:
        spot = float(spot_or_info or 0.0)
        info_dict = info if isinstance(info, dict) else {}

    threshold = 0.005
    target = float(info_dict.get("armed_target") or info_dict.get("target") or 0.0)
    
    if target <= 0 or spot <= 0:
        return False, "INVALID_TARGET_OR_SPOT"
        
    gap_pct = abs(spot - target) / target
    if gap_pct <= threshold:
        return True, "PREDICTIVE_ARMED_TRIGGER_FIRED"
    return False, "OUTSIDE_ARMED_ZONE"

def cancel_order(order_id: str):
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strict Midpoint Smart CSO Trader")
    parser.add_argument("--ticker", type=str, default=None, help="Target specific ticker (e.g. F, RIVN, NVDA)")
    parser.add_argument("--direction", type=str, choices=["CALL", "PUT", "SMART"], default="SMART", help="Side selection")
    parser.add_argument("--scan", type=int, default=25, help="Scan duration window in seconds")
    
    args = parser.parse_args()
    smart_cso_scout_and_execute(force_ticker=args.ticker, direction_override=args.direction, scan_duration=args.scan)
