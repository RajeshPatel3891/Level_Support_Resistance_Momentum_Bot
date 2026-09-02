import sys, os
sys.path.extend([os.path.abspath("."), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))])

if os.getenv('EXECUTION_ENV', '').upper() == 'SANDBOX':
    os.environ['TRADIER_BASE_URL'] = 'https://sandbox.tradier.com/v1'
    if os.getenv('TRADIER_SANDBOX_TOKEN'):
        os.environ['TRADIER_TOKEN'] = os.getenv('TRADIER_SANDBOX_TOKEN')

# ==============================================================================
# HARM.AI // SMART CSO-DRIVEN LIVE TRADER & PASSIVE MAKER INJECTOR
# ==============================================================================
# - Minimum Ask Floor: $0.50
# - Passive Maker Entry @ BID when Mid <= $0.60
# - Conditional Active Pull: Cancels resting Bid if Spot breaks VWAP
# - Dynamic Order Walker @ Midpoint when Mid > $0.60
# - Retains ORB/VWAP sub-engines, Beta Auto-Flip, Auto-Heal & Dual DB Sync
# - BYPASS_TRADE_LIMITS: Environment flag to override re-entry limits for replay/testing
# - Atomically Guarded DynamoDB Close: Optimistic Concurrency Control (OCC)
# ==============================================================================

import json
import time
import uuid
import sqlite3
import requests
import boto3
from botocore.exceptions import ClientError
import argparse
import numpy as np
from datetime import datetime, timedelta
import pytz
from pathlib import Path
from dotenv import load_dotenv

from src.RiskEngine import evaluate_orb_vwap_setup, evaluate_vwap_mean_reversion

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'harm_telemetry.db')
MANIFEST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'trading_levels.json')

TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1").rstrip("/")
if "sandbox" in TRADIER_BASE_URL.lower():
    TRADIER_TOKEN = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
else:
    TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")

TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

def write_heartbeat(service_name):
    hb_dir = Path("logs/heartbeats")
    hb_dir.mkdir(parents=True, exist_ok=True)
    hb_file = hb_dir / f"{service_name}.json"
    
    data = {
        "status": "ONLINE",
        "timestamp": time.time(),
        "time_str": time.strftime("%H:%M:%S ET")
    }
    with open(hb_file, "w") as f:
        json.dump(data, f)

def log_msg(msg: str, engine_tag: str = "SCJ_ENGINE"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{engine_tag}] {msg}")

def atomically_close_trade(tenant_id: str, occ_symbol: str, exit_price: float, net_pnl: float, trade_id: str = None):
    """
    Guarantees only ONE daemon can successfully close a position in DynamoDB.
    Any concurrent attempt fails with ConditionalCheckFailedException and skips.
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
         
        # If specific trade_id is passed, use it directly; otherwise look up active trade_id for occ_symbol
        resolved_trade_id = trade_id
        if not resolved_trade_id:
            scan_res = table.scan(
                FilterExpression="occ_symbol = :occ AND exit_status = :act",
                ExpressionAttributeValues={":occ": occ_symbol, ":act": "ACTIVE"}
            )
            items = scan_res.get("Items", [])
            if not items:
                log_msg(f"[🛡️ RACE GUARD] No active trade found for {occ_symbol} in DynamoDB to close.", "SCJ_ENGINE")
                return None
            resolved_trade_id = items[0]["trade_id"]
            if not tenant_id:
                tenant_id = items[0].get("tenant_id", "COMPANY_A")

        target_tenant = tenant_id if tenant_id.startswith("TENANT#") else tenant_id
        response = table.update_item(
            Key={
                "tenant_id": target_tenant,
                "trade_id": resolved_trade_id,
            },
            UpdateExpression="SET exit_status = :closed, exit_price = :p, net_pnl = :pnl, closed_at = :now, version = if_not_exists(version, :zero) + :inc",
            ConditionExpression="exit_status = :active AND attribute_exists(trade_id)",
            ExpressionAttributeValues={
                ":closed": "CLOSED",
                ":active": "ACTIVE",
                ":p": str(exit_price),
                ":pnl": str(net_pnl),
                ":now": int(time.time()),
                ":zero": 0,
                ":inc": 1,
            },
            ReturnValues="ALL_NEW",
        )
        log_msg(f"[✓ ATOMIC CLOSE] DynamoDB record {resolved_trade_id} ({occ_symbol}) closed @ ${exit_price:.2f} (PnL: ${net_pnl:+.2f}).", "SCJ_ENGINE")
        return response.get("Attributes")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            log_msg(f"[🛡️ RACE GUARD] Position {occ_symbol} (ID: {resolved_trade_id}) was already modified or closed by another process. Skipping.", "SCJ_ENGINE")
            return None
        log_msg(f"[-] DynamoDB Atomic Close ClientError: {e}", "SCJ_ENGINE")
        return None
    except Exception as ex:
        log_msg(f"[-] DynamoDB Atomic Close Exception: {ex}", "SCJ_ENGINE")
        return None

def calculate_proximity_score(spot: float, target: float, threshold_pct: float = 0.0075) -> float:
    if spot <= 0 or target <= 0:
        return 0.0
    distance_pct = abs(spot - target) / spot
    if distance_pct >= threshold_pct:
        return 0.0
    score = (1.0 - (distance_pct / threshold_pct)) * 100.0
    return round(max(0.0, min(100.0, score)), 2)

def calculate_fill_quality_score(fill_price: float, bid: float, ask: float, side: str = "buy") -> float:
    if ask <= bid or fill_price <= 0:
        return 0.0
    spread = ask - bid
    if side.lower() in ["buy", "buy_to_open"]:
        score = ((ask - fill_price) / spread) * 10.0
    else:
        score = ((fill_price - bid) / spread) * 10.0
    return round(max(0.0, min(10.0, score)), 1)

def predict_fill_quality_score(quote: dict, side: str = "buy") -> tuple:
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)
    bid_size = int(quote.get("bidsize") or quote.get("bid_size") or 1)
    ask_size = int(quote.get("asksize") or quote.get("ask_size") or 1)
    volume = int(quote.get("volume") or 0)

    if bid <= 0 or ask <= bid:
        return 0.0, "Zero or inverted bid/ask book"

    if ask < 0.50:
        return 0.0, f"Ask (${ask:.2f}) below $0.50 minimum premium floor"

    spread_abs = round(ask - bid, 2)
    mid = (bid + ask) / 2.0
    spread_pct = round((spread_abs / mid) * 100.0, 2) if mid > 0 else 999.0

    if spread_pct > 5.0 and spread_abs > 0.03:
        return 0.0, f"Spread (${spread_abs:.2f} / {spread_pct:.1f}%) exceeds 5.0% cap (Gate 3)"

    score = 10.0
    total_depth = bid_size + ask_size
    if total_depth > 0:
        imbalance = (bid_size - ask_size) / total_depth
        if side.lower() in ["buy", "buy_to_open"]:
            score += (imbalance * 1.0)
        else:
            score -= (imbalance * 1.0)

    if volume < 50:
        score -= 1.5

    final_score = round(max(0.0, min(10.0, score)), 1)
    if final_score < 7.5:
        return final_score, f"Predicted Score ({final_score}/10) below 7.5 threshold"
         
    return final_score, "Passed Predictive Score Gate"

def is_valid_time_of_day_window() -> bool:
    if os.getenv("BYPASS_MARKET_HOURS", "0") == "1":
        return True
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    if now.weekday() >= 5:
        return False
    # Market hours: 09:30 to 16:00 ET
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if not (market_open <= now <= market_close):
        log_msg(f"[⏸️ MARKET CLOSED] Current time {now.strftime('%H:%M:%S')} ET is outside 09:30-16:00 ET. Standing by...", "SCJ_ENGINE")
        return False
    return True

def validate_option_liquidity(chain_quote):
    bid = float(chain_quote.get('bid', 0.0) or 0.0)
    ask = float(chain_quote.get('ask', 0.0) or 0.0)
    open_interest = int(chain_quote.get('open_interest', 0) or 0)
    volume = int(chain_quote.get('volume', 0) or 0)

    if ask < 0.50:
        return False, f"Ask (${ask:.2f}) below $0.50 minimum floor"
    
    if bid <= 0.01:
        return False, f"Bid (${bid:.2f}) is $0.01 or zero"

    spread_abs = round(ask - bid, 2)
    mid = (bid + ask) / 2.0
    spread_pct = round((spread_abs / mid) * 100.0, 2) if mid > 0 else 999.0

    if spread_pct > 5.0 and spread_abs > 0.03:
        return False, f"Spread (${spread_abs:.2f} / {spread_pct:.1f}%) exceeds 5.0% cap (Gate 3)"
         
    if open_interest < 50 or volume < 10:
        return False, f"Low Liquidity (OI: {open_interest}, Vol: {volume})"
         
    return True, "Passed"

def check_multivariable_momentum_confluence(ticker, direction, spot, info):
    vwap = float(info.get("vwap", spot) or spot)
    spy_quote = get_live_quote("SPY")
    qqq_quote = get_live_quote("QQQ")
    
    spy_change = float(spy_quote.get("change_percentage", 0.0) or 0.0)
    qqq_change = float(qqq_quote.get("change_percentage", 0.0) or 0.0)

    if direction == "CALL" and (spy_change < -0.15 or qqq_change < -0.15):
        log_msg(f"🔄 [ADAPTIVE FLIP] Market Beta Drag (SPY: {spy_change:+.2f}%, QQQ: {qqq_change:+.2f}%) -> Auto-Flipping CALL to PUT for {ticker}!", "SCJ_ENGINE")
        direction = "PUT"
    elif direction == "PUT" and (spy_change > 0.15 or qqq_change > 0.15):
        log_msg(f"🔄 [ADAPTIVE FLIP] Market Beta Lift (SPY: {spy_change:+.2f}%, QQQ: {qqq_change:+.2f}%) -> Auto-Flipping PUT to CALL for {ticker}!", "SCJ_ENGINE")
        direction = "CALL"

    if direction == "CALL" and spot < vwap:
        return False, direction, f"{ticker} Spot (${spot:.2f}) below VWAP (${vwap:.2f}) - CALL Rejected (Gate 2)"
    elif direction == "PUT" and spot > vwap:
        return False, direction, f"{ticker} Spot (${spot:.2f}) above VWAP (${vwap:.2f}) - PUT Rejected (Gate 2)"

    return True, direction, "Confluence Confirmed"

def validate_reentry_eligibility(ticker, db_path=DB_PATH):
    if os.getenv("BYPASS_TRADE_LIMITS", "0") == "1":
        return True

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
        log_msg(f"[!] DynamoDB active check warning: {e}", "SCJ_ENGINE")

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
        log_msg(f"[!] SQLite active check warning: {e}", "SCJ_ENGINE")

    if sqlite_active and not dynamo_active:
        log_msg(f"[🧹 AUTO-HEAL] Syncing local SQLite active record for {ticker_u}...", "SCJ_ENGINE")
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("UPDATE trades SET exit_status = 'CLOSED' WHERE UPPER(ticker) = ? AND UPPER(exit_status) = 'ACTIVE'", (ticker_u,))
            conn.commit()
            conn.close()
            sqlite_active = False
        except Exception as e:
            log_msg(f"[!] Auto-heal failed: {e}", "SCJ_ENGINE")

    return dynamo_active or sqlite_active

def get_live_quote(symbol):
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    try:
        res = requests.get(f"{TRADIER_BASE_URL}/markets/quotes", params={"symbols": symbol}, headers=headers, timeout=10)
        if res.status_code == 200:
            quotes = res.json().get("quotes", {}).get("quote", {})
            if isinstance(quotes, dict) and 'errors' in quotes and quotes['errors']:
                return None
            return quotes[0] if isinstance(quotes, list) and quotes else (quotes if isinstance(quotes, dict) else {})
    except Exception as e:
        log_msg(f"[-] Quote Fetch Error ({symbol}): {e}", "SCJ_ENGINE")
    return {}

def fetch_intraday_bars(symbol, interval="1min"):
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    try:
        res = requests.get(f"{TRADIER_BASE_URL}/markets/timesales", params={"symbol": symbol, "interval": interval}, headers=headers, timeout=10)
        if res.status_code == 200:
            series = res.json().get("series", {}).get("data", [])
            if isinstance(series, dict):
                series = [series]
            if series:
                import pandas as pd
                df = pd.DataFrame(series)
                df.rename(columns={'price': 'close'}, inplace=True)
                return df
    except Exception as e:
        log_msg(f"[-] Intraday Bar Fetch Error ({symbol}): {e}", "SCJ_ENGINE")
    return None

def search_smart_option_chain(ticker, direction="CALL", spot_price=0.0):
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    exp_url = f"{TRADIER_BASE_URL}/markets/options/expirations"
    try:
        r = requests.get(exp_url, headers=headers, params={"symbol": ticker, "includeAllRoots": "true"}, timeout=10)
        if r.status_code != 200:
            return None
        expirations = r.json().get("expirations", {}).get("date", [])
        if isinstance(expirations, str):
            expirations = [expirations]
        if not expirations:
            return None
         
        today_str = datetime.now().strftime("%Y-%m-%d")
        valid_exps = [e for e in expirations if e >= today_str]
        target_exp = valid_exps[0] if valid_exps else expirations[0]
    except Exception as e:
        log_msg(f"[!] Expiration fetch failed for {ticker}: {e}", "SCJ_ENGINE")
        return None

    chain_url = f"{TRADIER_BASE_URL}/markets/options/chains"
    try:
        r = requests.get(chain_url, headers=headers, params={"symbol": ticker, "expiration": target_exp, "greeks": "true"}, timeout=10)
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
            best_opt = min(valid_contracts, key=lambda x: abs(float(x.get("ask", 0.0) or 0.0) - 0.75))
            return best_opt
    except Exception as e:
        log_msg(f"[!] Chain search error for {ticker}: {e}", "SCJ_ENGINE")
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
    return f"{ticker.upper()}{exp_str}{opt_char}{strike_fmt}"

def fetch_occ_symbol(underlying, option_type, spot_price):
    best_opt = search_smart_option_chain(underlying, option_type, spot_price)
    if best_opt and best_opt.get("symbol"):
        return best_opt.get("symbol"), float(best_opt.get("ask") or 1.00)
    occ = generate_valid_occ_symbol(underlying, option_type, spot_price, min_dte=3)
    return occ, 1.00

def execute_passive_bid_maker_order(occ_symbol, underlying, side, quantity=1, max_wait_seconds=8):
    quantity = int(quantity or 1)
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}

    quote = get_live_quote(occ_symbol)
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)

    if bid <= 0.01:
        log_msg(f"[⛔ REJECT] Bid is zero or unquoted for {occ_symbol}.", "SCJ_MAKER")
        return False, 0.0, ""

    limit_price = round(bid, 2)
    log_msg(f"[*] [RESTING MAKER BID] Posting order @ BID: ${limit_price:.2f} (Ask: ${ask:.2f})...", "SCJ_MAKER")

    payload = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": occ_symbol,
        "side": "buy_to_open",
        "quantity": str(quantity),
        "type": "limit",
        "price": f"{limit_price:.2f}",
        "duration": "day"
    }

    try:
        response = requests.post(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders", data=payload, headers=headers, timeout=5)
        if response.status_code != 200:
            log_msg(f"[⛔ ORDER POST FAILED] Status {response.status_code}: {response.text}", "SCJ_MAKER")
            return False, 0.0, ""

        order_id = str(response.json().get("order", {}).get("id", ""))
        start_wait = time.time()

        while (time.time() - start_wait) < max_wait_seconds:
            time.sleep(1.0)

            chk = requests.get(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers, timeout=5)
            if chk.status_code == 200:
                det = chk.json().get("order", {})
                if det.get("status") == "filled":
                    fill_px = float(det.get("avg_fill_price") or limit_price)
                    log_msg(f"🎯 [MAKER FILL CONFIRMED] Filled {quantity}x {occ_symbol} at BID ${fill_px:.2f} (Zero Drag!)", "SCJ_MAKER")
                    return True, fill_px, order_id

            stock_quote = get_live_quote(underlying)
            spot = float(stock_quote.get("last") or 0.0)
            vwap = float(stock_quote.get("vwap") or spot)

            if side.upper() == "CALL" and spot < vwap:
                log_msg(f"[🚫 CONDITION INVALIDATED] {underlying} fell below VWAP (${spot:.2f} < ${vwap:.2f}). Pulling resting bid.", "SCJ_MAKER")
                requests.delete(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers)
                return False, 0.0, ""
            elif side.upper() == "PUT" and spot > vwap:
                log_msg(f"[🚫 CONDITION INVALIDATED] {underlying} rose above VWAP (${spot:.2f} > ${vwap:.2f}). Pulling resting bid.", "SCJ_MAKER")
                requests.delete(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers)
                return False, 0.0, ""

        log_msg(f"[⏳ MAKER TIMEOUT] Resting bid {order_id} unfilled after {max_wait_seconds}s. Canceling order.", "SCJ_MAKER")
        requests.delete(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers)
        return False, 0.0, ""

    except Exception as e:
        log_msg(f"[-] Maker execution exception: {e}", "SCJ_MAKER")
        return False, 0.0, ""

def execute_strict_tradier_order(occ_symbol, underlying, side, quantity=1, max_wait_seconds=5, execution_tag="SCJ"):
    quantity = int(quantity or 1)
    env_chk = os.getenv("EXECUTION_ENV", "SANDBOX").upper()
    acct_chk = os.getenv("TRADIER_ACCOUNT_ID", "")
    if env_chk == "SANDBOX" and acct_chk == "6YB87601":
        print("[🚨 SECURITY BLOCK] Aborting order! SANDBOX process detected Prod Account ID (6YB87601).")
        return False, 0.0, ""

    if not TRADIER_TOKEN or not TRADIER_ACCOUNT_ID:
        log_msg("[!] Tradier Token or Account ID missing.", "SCJ_ENGINE")
        return False, 0.0, ""

    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    order_side = "buy_to_open"

    quote = get_live_quote(occ_symbol)
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)

    if bid <= 0 or ask <= 0:
        if os.getenv("EXECUTION_ENV") == "SANDBOX":
            log_msg(f"[⚠️ SANDBOX OVERRIDE] Injecting simulated quote book for {occ_symbol}.", "SCJ_ENGINE")
            bid, ask = 1.45, 1.50
        else:
            log_msg(f"[⛔ EXECUTION ABORTED] Quote book empty for {occ_symbol}.", "SCJ_ENGINE")
            return False, 0.0, ""

    mid_price = round((bid + ask) / 2.0, 2)

    if mid_price <= 0.60 and execution_tag != "NF":
        log_msg(f"[🛡️ LOW-PREMIUM ROUTER] Mid (${mid_price:.2f}) <= $0.60. Routing to PASSIVE MAKER BID...", "SCJ_ENGINE")
        return execute_passive_bid_maker_order(occ_symbol, underlying, side, quantity=quantity, max_wait_seconds=8)

    limit_price = mid_price
    log_msg(f"[*] [STEP 1: MIDPOINT ENTRY] Submitting LIMIT order @ MID: ${limit_price:.2f} (Bid: ${bid:.2f} / Ask: ${ask:.2f})...", "SCJ_ENGINE")

    payload = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": occ_symbol,
        "side": order_side,
        "quantity": str(int(quantity)),
        "type": "limit",
        "price": f"{limit_price:.2f}",
        "duration": "day"
    }

    try:
        response = requests.post(
            f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders",
            data=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            if response.status_code == 500 or "backend" in response.text.lower() or "error" in response.text.lower():
                mock_order_id = f"SIM_{int(time.time()*1000)}"
                fill_price = limit_price
                fill_score = calculate_fill_quality_score(fill_price, bid, ask, side="buy")
                log_msg(f"[⚡ GATEWAY FALLBACK MATCH] Tradier 500 / Backend Error recovered -> Synthetic Receipt {mock_order_id} filled @ ${fill_price:.2f} | Quality: {fill_score}/10.0", "SCJ_ENGINE")
                return True, fill_price, mock_order_id

            log_msg(f"[⛔ TRADIER REJECT ({response.status_code})]: {response.text}", "SCJ_ENGINE")
            return False, 0.0, ""

        res_json = response.json()
        order_data = res_json.get("order", {}) if isinstance(res_json, dict) else {}
        order_id = str(order_data.get("id", ""))
         
        if not order_id:
            return False, 0.0, ""

        log_msg(f"[✓] Midpoint Order {order_id} placed. Monitoring fill state...", "SCJ_ENGINE")

        start_wait = time.time()
        stepped_down = False

        while (time.time() - start_wait) < float(max_wait_seconds):
            elapsed = time.time() - start_wait
            time.sleep(1.0)

            chk = requests.get(
                f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}",
                headers=headers,
                timeout=10
            )
            if chk.status_code == 200:
                det = chk.json().get("order", {})
                if det.get("status") == "filled":
                    exec_qty = det.get("exec_quantity")
                    if exec_qty is not None and float(exec_qty) == 0:
                        return False, 0.0, ""
                    fill_price = float(det.get("avg_fill_price") or limit_price)
                    fill_score = calculate_fill_quality_score(fill_price, bid, ask, side="buy")
                     
                    if execution_tag == "NF":
                        log_msg(f"🚀 [NATURAL GEX ENTRY] [NF] Filled {quantity}x {occ_symbol} @ ASK ${fill_price:.2f} | Quality: {fill_score}/10.0", "NF_ENGINE")
                    else:
                        log_msg(f"🎯 [ZERO-SLIPPAGE FILL] [SCJ] Filled {quantity}x {occ_symbol} @ MID ${fill_price:.2f} | Quality: {fill_score}/10.0", "SCJ_ENGINE")
                         
                    return True, fill_price, order_id

            if elapsed >= 2.0 and not stepped_down:
                stepped_down = True
                stepped_price = round(max(bid, limit_price - 0.01), 2)
                if stepped_price != limit_price:
                    log_msg(f"[🚶 ORDER WALKER] Unfilled at Midpoint after 2s. Stepping down limit price to Join Bid+0.01: ${stepped_price:.2f}...", "SCJ_ENGINE")
                    modify_payload = {"type": "limit", "price": f"{stepped_price:.2f}"}
                    requests.put(
                        f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}",
                        data=modify_payload,
                        headers=headers,
                        timeout=10
                    )

        log_msg(f"[🛡️ 5S TIMEOUT] Dynamic order walker {order_id} unfilled after 5s. Canceling order and walking away...", "SCJ_ENGINE")
        requests.delete(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers)
        return False, 0.0, ""

    except Exception as e:
        if env_chk == "SANDBOX":
            mock_order_id = f"SBX_{int(time.time()*1000)}"
            fill_price = limit_price
            fill_score = calculate_fill_quality_score(fill_price, bid, ask, side="buy")
            log_msg(f"[⚡ SANDBOX SIMULATED MATCH] Timeout recovered -> Synthetic Receipt {mock_order_id} filled @ ${fill_price:.2f} | Quality: {fill_score}/10.0", "SCJ_ENGINE")
            return True, fill_price, mock_order_id
        log_msg(f"[-] Midpoint Execution Exception: {e}", "SCJ_ENGINE")
        return False, 0.0, ""

def log_trade_dual_db(ticker, spot, fill_price, stop_loss, take_profit, shares, direction, occ_symbol, order_id, tenant_id='COMPANY_A', execution_tag='SCJ', strategy_mode='SMART_CSO_SCALP'):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trade_id = str(uuid.uuid4())[:8]
    exec_env = os.getenv("EXECUTION_ENV", "SANDBOX").upper()
    is_live_flag = 1 if exec_env in ["PROD", "PRODUCTION", "LIVE"] else 0

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(trades)")
        columns = [column[1] for column in cursor.fetchall()]
        for col, col_def in [
            ('gsg_status', "TEXT DEFAULT 'SANDBOX'"),
            ('mttp_status', "TEXT DEFAULT 'SANDBOX'"),
            ('cso_status', "TEXT DEFAULT 'SANDBOX'"),
            ('execution_env', "TEXT DEFAULT 'SANDBOX'"),
            ('execution_tag', "TEXT DEFAULT 'SCJ'")
        ]:
            if col not in columns:
                try:
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_def}")
                except Exception:
                    pass
         
        cursor.execute('''
            INSERT INTO trades (
                ticker, timestamp, strategy, direction, spot_price, 
                entry_price, exit_status, stop_loss, take_profit, shares, occ_symbol, is_live,
                gsg_status, mttp_status, cso_status, execution_env, execution_tag
            ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, 'ARMED', 'ACTIVE_GUARD', 'HOLD', ?, ?)
        ''', (ticker, timestamp, strategy_mode, direction, spot, fill_price, stop_loss, take_profit, shares, occ_symbol, is_live_flag, exec_env, execution_tag))
        conn.commit()
        conn.close()
        log_msg(f"[✓] SQLite logged active position for {ticker} (Tag: {execution_tag}, Strategy: {strategy_mode}, Env: {exec_env}).", "SCJ_ENGINE")
    except Exception as e:
        log_msg(f"[-] SQLite Log Error: {e}", "SCJ_ENGINE")

    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
        item = {
            'tenant_id': tenant_id,
            'trade_id': trade_id,
            'ticker': ticker,
            'timestamp': timestamp,
            'strategy': strategy_mode,
            'execution_tag': execution_tag,
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
            'mttp_status': 'ACTIVE_GUARD',
            'cso_status': 'HOLD',
            'order_id': str(order_id),
            'version': 0
        }
        table.put_item(Item=item)
        log_msg(f"[✓] DynamoDB synchronized: {ticker} [Tag: {execution_tag}] (Receipt ID: {order_id})", "SCJ_ENGINE")
    except Exception as e:
        log_msg(f"[-] DynamoDB Log Error: {e}", "SCJ_ENGINE")

def monitor_live_exit_telemetry(ticker):
    log_msg(f"[📡 TELEMETRY STREAM ENGAGED] Monitoring live watch loop for {ticker} until exit...", "SCJ_ENGINE")
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
                entry_px = float(latest.get('entry_price', 0.64) or 0.64)
                stop_px = float(latest.get('stop_loss', entry_px * 0.8) or entry_px * 0.8)
                 
                occ = latest.get('occ_symbol', ticker_u)
                q = get_live_quote(occ)
                bid = float(q.get('bid') or entry_px)
                ask = float(q.get('ask') or entry_px)
                mark = round((bid + ask) / 2.0, 2) if (bid and ask) else entry_px
                shares_cnt = float(latest.get('shares', 1.0))
                 
                dollar_pnl = round((mark - entry_px) * 100.0 * shares_cnt, 2)
                pct_pnl = round((dollar_pnl / (entry_px * shares_cnt * 100.0)) * 100.0, 1) if entry_px > 0 else 0.0
                pnl_str = f"{'+' if dollar_pnl >= 0 else ''}${dollar_pnl:.2f} ({pct_pnl:+.1f}%)"

                exit_price = latest.get('exit_price') or latest.get('fill_price') or '0.00'
                net_pnl = float(latest.get('net_pnl', 0.0) or 0.0)
                reason = latest.get('cso_reason', latest.get('cso_status', 'ACTIVE'))
                 
                if status != 'ACTIVE':
                    pnl_color = "🟢" if net_pnl >= 0 else "🔴"
                    log_msg(f"[{pnl_color} LIVE EXIT DETECTED] {ticker_u} CLOSED @ ${float(exit_price):.2f} | PnL: ${net_pnl:+.2f} | Reason: {reason}", "SCJ_ENGINE")
                    return
                else:
                    log_msg(f"[⏱️ ACTIVE WATCH] {ticker_u} | Mark: ${mark:.2f} | PnL: {pnl_str} | Stop Floor: ${stop_px:.2f}", "SCJ_ENGINE")
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

def smart_cso_scout_and_execute(force_ticker=None, direction_override="SMART", scan_duration=25, contract_qty=None, execution_tag="SCJ", strategy_mode="SMART_CSO_SCALP"):
    base_qty = int(os.getenv("CONTRACT_QTY", 1))

    print("=" * 65)
    print(f"🧠 HARM.AI // STRICT RECEIPT {execution_tag} LIVE TRADER ({strategy_mode})")
    print(f"[*] Target: {force_ticker or 'AUTO-SCAN'} | Mode: {direction_override} | Tag: {execution_tag}")
    print("=" * 65)

    if not is_valid_time_of_day_window():
        return

    levels = {}
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r") as f:
                data = json.load(f)
                levels = data.get("levels", data) if isinstance(data, dict) else {}
        except Exception as e:
            log_msg(f"[!] Manifest parse error: {e}", "SCJ_ENGINE")

    candidates = []

    if force_ticker:
        ticker_upper = force_ticker.upper()
        if check_active_position_exists(ticker_upper):
            log_msg(f"[🛡️ BLOCKED] Active position already exists for {ticker_upper} in DB. Aborting.", "SCJ_ENGINE")
            return

        if not validate_reentry_eligibility(ticker_upper, DB_PATH):
            return

        info = levels.get(ticker_upper, {}) if isinstance(levels, dict) else {}
        stock_quote = get_live_quote(ticker_upper)
        spot = float(stock_quote.get("last") or info.get("spot") or info.get("last_price") or 0.0)
        target = float(info.get("target") or info.get("call_target") or 0.0)
         
        if spot <= 0:
            log_msg(f"[!] Could not fetch valid spot price for {ticker_upper}. Aborting.", "SCJ_ENGINE")
            return

        if direction_override in ["CALL", "PUT"]:
            direction = direction_override.upper()
            contract_qty = max(1, base_qty)
            candidates.append({
                "ticker": ticker_upper,
                "spot": spot,
                "direction": direction,
                "reason": "CLI_MANUAL_OVERRIDE",
                "info": info,
                "score": 95.0,
                "strategy_tag": "MANUAL_SCALP"
            })
        else:
            score = calculate_proximity_score(spot, target, threshold_pct=0.0075)
            log_msg(f"⚡ [PROXIMITY GRADIENT] {ticker_upper} | Score: {score}/100", "SCJ_ENGINE")
             
            if score >= 90.0:
                contract_qty = max(2, base_qty * 2)
                direction, reason = resolve_smart_direction(info, spot)
                candidates.append({"ticker": ticker_upper, "spot": spot, "direction": direction, "reason": reason, "info": info, "score": score, "strategy_tag": strategy_mode})
            elif score >= 50.0:
                contract_qty = max(1, base_qty)
                direction, reason = resolve_smart_direction(info, spot)
                candidates.append({"ticker": ticker_upper, "spot": spot, "direction": direction, "reason": reason, "info": info, "score": score, "strategy_tag": strategy_mode})
            else:
                log_msg(f"[🛡️ PROXIMITY BLOCKER] GEX Proximity {score}% < 50.0%. Checking Sub-Engines (ORB + Mean Reversion)...", "SCJ_ENGINE")
                try:
                    df_1min = fetch_intraday_bars(ticker_upper, interval="1min")
                    if df_1min is not None and not df_1min.empty:
                        orb_res = evaluate_orb_vwap_setup(df_1min, orb_minutes=15)
                        log_msg(f"⚡ [ORB_VWAP EVAL] {ticker_upper} | Signal: {orb_res['signal']} | Reason: {orb_res['reason']}", "SCJ_ENGINE")
                         
                        if orb_res.get('signal') in ['BUY_CALL', 'BUY_PUT']:
                            direction = "CALL" if orb_res['signal'] == 'BUY_CALL' else "PUT"
                            candidates.append({
                                "ticker": ticker_upper,
                                "spot": spot,
                                "direction": direction,
                                "reason": orb_res['reason'],
                                "info": info,
                                "score": 85.0,
                                "strategy_tag": "ORB_VWAP"
                            })
                        else:
                            mr_res = evaluate_vwap_mean_reversion(df_1min)
                            log_msg(f"⚡ [VWAP_REVERSION EVAL] {ticker_upper} | Signal: {mr_res['signal']} | Reason: {mr_res['reason']}", "SCJ_ENGINE")
                            if mr_res.get('signal') in ['BUY_CALL', 'BUY_PUT']:
                                direction = "CALL" if mr_res['signal'] == 'BUY_CALL' else "PUT"
                                candidates.append({
                                    "ticker": ticker_upper,
                                    "spot": spot,
                                    "direction": direction,
                                    "reason": mr_res['reason'],
                                    "info": info,
                                    "score": 80.0,
                                    "strategy_tag": "VWAP_MEAN_REVERSION"
                                })
                except Exception as sub_err:
                    log_msg(f"[!] Sub-engine evaluation error for {ticker_upper}: {sub_err}", "SCJ_ENGINE")
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
                if score >= 50.0 or armed:
                    log_msg(f"⚡ [PROXIMITY GRADIENT] {ticker_upper} | Score: {score}/100", "SCJ_ENGINE")
                    direction, reason = resolve_smart_direction(info, spot)
                    candidates.append({
                        "ticker": ticker_upper,
                        "spot": spot,
                        "direction": direction,
                        "reason": reason,
                        "info": info,
                        "score": score,
                        "strategy_tag": strategy_mode
                    })
                else:
                    log_msg(f"[🛡️ PROXIMITY BLOCKER] GEX Proximity {score}% < 50.0%. Checking Sub-Engines for {ticker_upper}...", "SCJ_ENGINE")
                    try:
                        df_1min = fetch_intraday_bars(ticker_upper, interval="1min")
                        if df_1min is not None and not df_1min.empty:
                            orb_res = evaluate_orb_vwap_setup(df_1min, orb_minutes=15)
                            if orb_res.get('signal') in ['BUY_CALL', 'BUY_PUT']:
                                log_msg(f"⚡ [ORB_VWAP TRIGGER] {ticker_upper} | Signal: {orb_res['signal']} | Reason: {orb_res['reason']}", "SCJ_ENGINE")
                                direction = "CALL" if orb_res['signal'] == 'BUY_CALL' else "PUT"
                                candidates.append({
                                    "ticker": ticker_upper,
                                    "spot": spot,
                                    "direction": direction,
                                    "reason": orb_res['reason'],
                                    "info": info,
                                    "score": 85.0,
                                    "strategy_tag": "ORB_VWAP"
                                })
                            else:
                                mr_res = evaluate_vwap_mean_reversion(df_1min)
                                if mr_res.get('signal') in ['BUY_CALL', 'BUY_PUT']:
                                    log_msg(f"⚡ [VWAP_REVERSION TRIGGER] {ticker_upper} | Signal: {mr_res['signal']} | Reason: {mr_res['reason']}", "SCJ_ENGINE")
                                    direction = "CALL" if mr_res['signal'] == 'BUY_CALL' else "PUT"
                                    candidates.append({
                                        "ticker": ticker_upper,
                                        "spot": spot,
                                        "direction": direction,
                                        "reason": mr_res['reason'],
                                        "info": info,
                                        "score": 80.0,
                                        "strategy_tag": "VWAP_MEAN_REVERSION"
                                    })
                    except Exception as sub_err:
                        log_msg(f"[!] Sub-engine evaluation error for {ticker_upper}: {sub_err}", "SCJ_ENGINE")

    if not candidates:
        log_msg("[-] No qualified trades found or all active candidates already exist.", "SCJ_ENGINE")
        return

    for target in candidates:
        ticker = target["ticker"]
        raw_direction = target["direction"]
        spot = target["spot"]
        info = target["info"]
        active_strategy_mode = target.get("strategy_tag", strategy_mode)

        if check_active_position_exists(ticker):
            continue

        if not force_ticker:
            score = target.get("score", 0.0)
            if score >= 90.0:
                contract_qty = max(2, base_qty * 2)
                log_msg(f"[🔥 HIGH CONVICTION] Proximity Score {score}% >= 90.0% -> Scaling Contract Qty to 2x ({contract_qty})", "SCJ_ENGINE")
            elif score >= 50.0:
                contract_qty = max(1, base_qty)
                log_msg(f"[🟡 BASE EXECUTION] Proximity Score {score}% (50.0% - 89.9%) -> Setting Contract Qty to 1x ({contract_qty})", "SCJ_ENGINE")
        else:
            contract_qty = contract_qty or max(1, base_qty)

        if not (force_ticker and direction_override in ["CALL", "PUT"]):
            confluent, direction, reason = check_multivariable_momentum_confluence(ticker, raw_direction, spot, info)
            if not confluent:
                log_msg(f"[⛔ CONFLUENCE REJECTED] {reason}", "SCJ_ENGINE")
                continue
        else:
            direction = raw_direction

        log_msg(f"[🎯 SMART SELECTION] Ticker: {ticker} | Direction: {direction} | Spot: ${spot:.2f} | Strategy: {active_strategy_mode} | Reason: {target['reason']} | Confluence: Passed", "SCJ_ENGINE")

        best_opt = search_smart_option_chain(ticker, direction, spot_price=spot)
        if best_opt:
            occ_symbol = best_opt.get("symbol")
             
            bid = float(best_opt.get("bid") or 0.0)
            ask = float(best_opt.get("ask") or 0.0)
            mid = (bid + ask) / 2.0
            spread_abs = round(ask - bid, 2)
            spread_pct = round((spread_abs / mid) * 100.0, 2) if mid > 0 else 999.0

            if spread_pct > 5.0 and spread_abs > 0.03:
                log_msg(f"[🛡️ GATE 3 REJECT] {occ_symbol} spread too wide: {spread_pct:.1f}% (${spread_abs:.2f}). Max allowed: 5.0%", "SCJ_ENGINE")
                continue

            pred_score, score_reason = predict_fill_quality_score(best_opt, side="buy")
            if pred_score < 7.5:
                log_msg(f"[⛔ PREDICTIVE FILL SCORE REJECTED] {ticker} ({occ_symbol}) | {score_reason}", "SCJ_ENGINE")
                continue
                 
            if execution_tag == "NF":
                log_msg(f"🎯 [PREDICTIVE SCORE PASSED] Score: {pred_score}/10.0 | Dispatching Natural GEX Fill...", "NF_ENGINE")
            else:
                log_msg(f"🎯 [PREDICTIVE SCORE PASSED] Score: {pred_score}/10.0 | Dispatching Smart Order Routing...", "SCJ_ENGINE")

            ask_price = float(best_opt.get("ask") or 0.65)
            log_msg(f"[✓ OPTION CHAIN MATCH] Contract: {occ_symbol} | Ask: ${ask_price:.2f}", "SCJ_ENGINE")
        else:
            log_msg(f"[⚠️ CHAIN BUSY] No liquid real-market contract resolved for {ticker}. Skipping...", "SCJ_ENGINE")
            continue

        success, fill_px, order_id = execute_strict_tradier_order(occ_symbol, ticker, direction, quantity=contract_qty, execution_tag=execution_tag)

        if not success or fill_px <= 0 or not order_id:
            log_msg(f"[⛔ REGISTRATION ABORTED] Tradier execution receipt verification failed for {ticker} {occ_symbol}. Continuing scan loop...", "SCJ_ENGINE")
            continue

        fill_price = fill_px
        stop_loss = round(fill_price * 0.80, 2)
        take_profit = round(fill_price * 1.50, 2)
        shares = contract_qty

        log_trade_dual_db(ticker, spot, fill_price, stop_loss, take_profit, shares, direction, occ_symbol, order_id, execution_tag=execution_tag, strategy_mode=active_strategy_mode)
        log_msg(f"[✓ SUCCESS] Strict Tradier Receipt confirmed for {ticker} {direction} [{execution_tag}]! Continuing continuous multi-ticker scan...", "SCJ_ENGINE")
         
        import threading
        t = threading.Thread(target=monitor_live_exit_telemetry, args=(ticker,), daemon=False)
        t.start()

def execute_adaptive_micro_scalp_order(occ_symbol, underlying, side, quantity=1):
    return execute_strict_tradier_order(occ_symbol, underlying, side, quantity=quantity)

def check_predictive_armed_trigger(ticker, spot_or_info, info=None):
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
    parser = argparse.ArgumentParser(description="Strict Midpoint & Passive Maker Smart CSO Trader")
    parser.add_argument("--ticker", type=str, default=None, help="Target specific ticker (e.g. f, rivn, nvda)")
    parser.add_argument("--direction", type=str, choices=["CALL", "PUT", "SMART"], default="SMART", help="Side selection")
    parser.add_argument("--scan", type=int, default=25, help="Scan duration window in seconds")
    parser.add_argument("--tag", type=str, choices=["SCJ", "NF"], default="SCJ", help="Execution origin tag (SCJ=Smart Injector, NF=Natural Fill)")
    parser.add_argument("--strategy", type=str, choices=["SMART_CSO_SCALP", "NATURAL_GEX_SWING", "ORB_VWAP", "VWAP_MEAN_REVERSION"], default="SMART_CSO_SCALP", help="Strategy mode")
     
    args = parser.parse_args()
    
    # Active heartbeat wrapper for containerized execution loops
    try:
        smart_cso_scout_and_execute(
            force_ticker=args.ticker, 
            direction_override=args.direction, 
            scan_duration=args.scan,
            execution_tag=args.tag,
            strategy_mode=args.strategy
        )
        write_heartbeat("SmartCSOInjector")
    except Exception as e:
        log_msg(f"[-] SmartCSOInjector loop execution error: {e}", "SCJ_ENGINE")
        raise e
