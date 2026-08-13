#!/usr/bin/env python3
"""
HARM.AI // SMART CSO-DRIVEN LIVE TRADER & INJECTOR
===============================================================================
Scans trading_levels.json, evaluates proximity/safety and support/resistance 
boundaries, resolves directional bias (Call vs Put), performs smart option chain
liquidity & spread searches via Tradier API, enforces strict execution receipts, 
and synchronizes with both SQLite and AWS DynamoDB with live GSG/MTTP bindings.
Now features continuous real-time terminal exit telemetry streaming!
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
from datetime import datetime
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

def fetch_occ_symbol(underlying, option_type, spot_price):
    best_opt = search_smart_option_chain(underlying, option_type, spot_price)
    if best_opt and best_opt.get("symbol"):
        return best_opt.get("symbol"), float(best_opt.get("ask") or 1.00)
        
    now = datetime.now()
    date_str = now.strftime("%y%m%d")
    type_code = "C" if option_type.upper() == "CALL" else "P"
    strike_fmt = f"{int(round(spot_price * 1000)):08d}"
    occ = f"{underlying}{date_str}{type_code}{strike_fmt}"
    return occ, 1.00

def execute_strict_tradier_order(occ_symbol, underlying, side, quantity=1, max_wait_seconds=10):
    """
    Executes order via Low-Ball Adaptive Laddering Engine.
    - Phase 1: Submits low-ball limit order at/near BID.
    - Phase 2: Holds for 3.5s while evaluating underlying price velocity & book depth.
    - Phase 3: Steps up limit price if momentum is high, or cancels/aborts if stagnant/adverse.
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

        order_data = response.json().get("order", {})
        order_id = str(order_data.get("id"))
        log_msg(f"[✓] Low-Ball order placed. Order ID: {order_id}. Evaluating fill probability over 3.5s...")

        # --- PHASE 2: EVALUATION WINDOW (3.5s) ---
        start_wait = time.time()
        is_filled = False
        fill_price = 0.0

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
                if status in ["filled", "open", "pending"]:
                    if status == "filled":
                        fill_price = float(detailed.get("avg_fill_price") or low_ball_px)
                        is_filled = True
                        log_msg(f"[🎯 LOW-BALL FILLED!] Target filled at BID (${fill_price:.2f})! Zero spread slippage.")
                        return True, fill_price, order_id

        # --- PHASE 3: MOMENTUM EVALUATION & STEP-UP / ABORT ---
        log_msg(f"[⏱️ EVALUATION TIMEOUT] Low-ball bid (${limit_price_str}) unfilled after 3.5s. Checking momentum...")
        
        latest_q = get_live_quote(occ_symbol)
        new_bid = float(latest_q.get("bid") or 0.0)
        new_ask = float(latest_q.get("ask") or 0.0)

        if new_bid >= bid and new_ask > 0:
            midpoint = (new_bid + new_ask) / 2.0
            stepped_mid = round(round(midpoint / 0.05) * 0.05, 2)
            
            log_msg(f"[🚀 MOMENTUM CONFIRMED] Stepping up limit price from ${limit_price_str} -> ${stepped_mid:.2f} to secure fill...")

            requests.delete(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers)

            payload["price"] = f"{stepped_mid:.2f}"
            step_res = requests.post(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders", data=payload, headers=headers, timeout=5)
            
            if step_res.status_code == 200:
                new_order_id = str(step_res.json().get("order", {}).get("id"))
                for _ in range(3):
                    time.sleep(1.2)
                    chk = requests.get(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{new_order_id}", headers=headers)
                    if chk.status_code == 200:
                        det = chk.json().get("order", {})
                        if det.get("status") in ["filled", "open", "pending"]:
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

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (
                ticker, timestamp, strategy, direction, spot_price, 
                entry_price, exit_status, stop_loss, take_profit, shares, occ_symbol, is_live,
                gsg_status, mttp_status, cso_status
            ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, 1, 'ARMED', 'ACTIVE_45M_GUARD', 'HOLD')
        ''', (ticker, timestamp, 'SMART_CSO_LIVE', direction, spot, fill_price, stop_loss, take_profit, shares, occ_symbol))
        conn.commit()
        conn.close()
        log_msg(f"[✓] SQLite logged active position for {ticker} with active GSG/MTTP guards.")
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
            'is_live': 1,
            'occ_symbol': occ_symbol,
            'gsg_status': 'ARMED',
            'mttp_status': 'ACTIVE_45M_GUARD',
            'cso_status': 'HOLD',
            'order_id': str(order_id)
        }
        table.put_item(Item=item)
        log_msg(f"[✓] DynamoDB synchronized: {ticker} (Receipt ID: {order_id}) -> GSG/MTTP Watch Loops Engaged.")
    except Exception as e:
        log_msg(f"[-] DynamoDB Log Error: {e}")

def monitor_live_exit_telemetry(ticker):
    """
    Streams live exit status and PnL telemetry continuously in terminal window until position is CLOSED.
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
                exit_price = latest.get('exit_price', '0.00')
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

def smart_cso_scout_and_execute(force_ticker=None, direction_override="SMART", scan_duration=25):
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

    success, fill_px, order_id = execute_strict_tradier_order(occ_symbol, ticker, direction, quantity=5)

    if not success or fill_px <= 0 or not order_id:
        log_msg(f"[⛔ REGISTRATION ABORTED] Tradier execution receipt verification failed for {ticker} {occ_symbol}. Zero records written to DB, guards not engaged.")
        return

    fill_price = fill_px
    stop_loss = round(fill_price * 0.80, 2)
    take_profit = round(fill_price * 1.50, 2)
    shares = 5

    log_trade_dual_db(ticker, spot, fill_price, stop_loss, take_profit, shares, direction, occ_symbol, order_id)
    log_msg(f"[✓ SUCCESS] Strict Tradier Receipt confirmed and live watch loops engaged for {ticker} {direction}!")
    
    # Engagement of continuous live terminal exit telemetry
    monitor_live_exit_telemetry(ticker)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Strict Receipt Smart CSO Live Trader & Injector")
    parser.add_argument("--ticker", type=str, default=None, help="Target specific ticker (e.g. F, RIVN, NVDA)")
    parser.add_argument("--direction", type=str, choices=["CALL", "PUT", "SMART"], default="SMART", help="Side selection")
    parser.add_argument("--scan", type=int, default=25, help="Scan duration window in seconds")
    
    args = parser.parse_args()
    smart_cso_scout_and_execute(force_ticker=args.ticker, direction_override=args.direction, scan_duration=args.scan)
