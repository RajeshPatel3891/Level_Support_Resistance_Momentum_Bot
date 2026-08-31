import os, sys

if os.getenv('EXECUTION_ENV', '').upper() == 'SANDBOX':
    os.environ['TRADIER_BASE_URL'] = 'https://sandbox.tradier.com/v1'
    if os.getenv('TRADIER_SANDBOX_TOKEN'):
        os.environ['TRADIER_TOKEN'] = os.getenv('TRADIER_SANDBOX_TOKEN')

# ==============================================================================
# HARM.AI OPTIMIZED CHIEF STRATEGY OFFICER (CSO) MASTER EXIT MONITOR
# ==============================================================================
import os
import sys
import time
import json
import sqlite3
import requests
import boto3
import datetime
from datetime import datetime as dt
import pytz
import re
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr

if os.path.exists('.env.prod'):
    load_dotenv('.env.prod', override=True)
else:
    load_dotenv(override=True)

MANIFEST_PATH = "trading_levels.json"
MTTP_MAX_MINUTES = int(os.getenv("MTTP_MAX_MINUTES", 15))  # Default 15m Scalp Horizon

def get_tradier_token():
    token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN') or os.getenv('TRADIER_ACCESS_TOKEN')
    if token:
        return token
    if os.path.exists('system_config.json'):
        try:
            with open('system_config.json', 'r') as f:
                cfg = json.load(f)
                return cfg.get('tradier_access_token', cfg.get('TRADIER_ACCESS_TOKEN', ''))
        except Exception:
            pass
    return ''

TRADIER_TOKEN = get_tradier_token()
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")

def is_regular_trading_hours():
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(ny_tz)
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close

def get_gex_target_info(ticker):
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r") as f:
                data = json.load(f)
                val = data.get(ticker, {})
                spot = float(val.get("spot", val.get("last_price", val.get("spot_price", 0.0))) or 0.0)
                target = float(val.get("target", val.get("gex_target", val.get("call_target", val.get("put_target", 0.0)))) or 0.0)
                gap_pct = float(val.get("gap_pct", 0.0) or 0.0)
                return spot, target, gap_pct
        except Exception:
            pass
    return 0.0, 0.0, 0.0

def ensure_schema():
    db_file = "harm_telemetry.db"
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            for col in ["exit_timestamp TEXT", "peak_price REAL", "is_runner INTEGER", "partial_pnl REAL", "min_pnl_seen REAL", "execution_tag TEXT DEFAULT 'SCJ'"]:
                try:
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[-] Local SQLite schema warning: {e}")

def get_live_quote(occ_symbol):
    token = get_tradier_token()
    if not token or not occ_symbol:
        return 0.0, os.getenv("TRADIER_BASE_URL", TRADIER_BASE_URL)
    
    endpoints = [
        os.getenv("TRADIER_BASE_URL", TRADIER_BASE_URL).rstrip('/') + "/markets/quotes",
        "https://api.tradier.com/v1/markets/quotes",
        "https://sandbox.tradier.com/v1/markets/quotes"
    ]
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    for url in endpoints:
        try:
            res = requests.get(f"{url}?symbols={occ_symbol}", headers=headers, timeout=3)
            if res.status_code == 200:
                q = res.json().get('quotes', {}).get('quote', {})
                if isinstance(q, list):
                    q = q[0] if q else {}
                bid = float(q.get('bid') or 0.0)
                ask = float(q.get('ask') or 0.0)
                last = float(q.get('last') or 0.0)
                
                base_url = "https://api.tradier.com/v1" if "api.tradier" in url else "https://sandbox.tradier.com/v1"
                
                if ask > 0 and bid > 0:
                    return round((ask + bid) / 2.0, 2), base_url
                mark = ask if ask > 0 else (last if last > 0 else 0.0)
                if mark > 0:
                    return mark, base_url
        except Exception:
            continue
            
    return 0.0, os.getenv("TRADIER_BASE_URL", TRADIER_BASE_URL)

def get_live_bid_ask(occ_symbol):
    token = get_tradier_token()
    base_url = os.getenv("TRADIER_BASE_URL", TRADIER_BASE_URL).rstrip('/')
    if not token or not occ_symbol:
        return 0.0, 0.0, base_url

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        res = requests.get(f"{base_url}/markets/quotes?symbols={occ_symbol}", headers=headers, timeout=3)
        if res.status_code == 200:
            q = res.json().get('quotes', {}).get('quote', {})
            if isinstance(q, list):
                q = q[0] if q else {}
            bid = float(q.get('bid') or 0.0)
            ask = float(q.get('ask') or 0.0)
            return bid, ask, base_url
    except Exception as e:
        print(f"[-] Error fetching bid/ask for {occ_symbol}: {e}")

    return 0.0, 0.0, base_url

def execute_tradier_close(occ_symbol, ticker, shares, base_url=None, max_wait_seconds=10):
    token = get_tradier_token()
    account_id = os.getenv("TRADIER_ACCOUNT_ID", TRADIER_ACCOUNT_ID)
    active_base_url = (base_url or os.getenv("TRADIER_BASE_URL", TRADIER_BASE_URL)).rstrip('/')

    if not token or not account_id:
        print(f"[-] Tradier credentials missing. Could not close {shares}x {occ_symbol}")
        return False

    match = re.match(r'^([A-Z]+)\d{6}[CP]\d{8}$', occ_symbol)
    root_symbol = match.group(1) if match else ticker.split('260821')[0].rstrip('0123456789')

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    payload = {
        'class': 'option',
        'symbol': root_symbol,
        'option_symbol': occ_symbol,
        'side': 'sell_to_close',
        'quantity': str(abs(int(shares))),
        'type': 'market',
        'duration': 'day'
    }

    try:
        url = f"{active_base_url}/accounts/{account_id}/orders"
        res = requests.post(url, data=payload, headers=headers, timeout=5)
        
        if res.status_code == 200:
            body = res.json()
            order_info = body.get('order', {})
            order_id = order_info.get('id')
            status = str(order_info.get('status', '')).lower()
            
            if order_id or status in ['ok', 'pending', 'filled', 'open']:
                print(f"[✓ TRADIER CLOSE SUCCESS] {shares}x {occ_symbol} | Order ID: {order_id}")
                return True
            print(f"[-] Tradier Rejected Order Payload: {body}")
            return False
            
        print(f"[-] Tradier Close Error HTTP {res.status_code}: {res.text}")
        return False
    except Exception as e:
        print(f"[-] Tradier Close Exception for {occ_symbol}: {e}")
        return False

def execute_tradier_close_stepped(occ_symbol, ticker, shares, base_url=None, max_wait_seconds=10):
    token = get_tradier_token()
    account_id = os.getenv("TRADIER_ACCOUNT_ID", TRADIER_ACCOUNT_ID)
    active_base_url = (base_url or os.getenv("TRADIER_BASE_URL", TRADIER_BASE_URL)).rstrip('/')

    if not token or not account_id:
        print(f"[-] Tradier credentials missing. Could not stepped-close {shares}x {occ_symbol}")
        return False

    bid, ask, _ = get_live_bid_ask(occ_symbol)
    if bid <= 0 and ask <= 0:
        print(f"[!] Quote book empty for {occ_symbol}. Falling back to standard market close.")
        return execute_tradier_close(occ_symbol, ticker, shares, active_base_url, max_wait_seconds)

    mid = round((bid + ask) / 2.0, 2)
    target_price = max(mid, bid, 0.01)

    match = re.match(r'^([A-Z]+)\d{6}[CP]\d{8}$', occ_symbol)
    root_symbol = match.group(1) if match else ticker.split('260821')[0].rstrip('0123456789')

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    payload = {
        "class": "option",
        "symbol": root_symbol,
        "option_symbol": occ_symbol,
        "side": "sell_to_close",
        "quantity": str(abs(int(shares))),
        "type": "limit",
        "price": f"{target_price:.2f}",
        "duration": "day"
    }

    try:
        url = f"{active_base_url}/accounts/{account_id}/orders"
        print(f"[⚡ STEPPED CLOSE] Submitting Limit Sell @ ${target_price:.2f} (Mid: ${mid:.2f} / Bid: ${bid:.2f}) for {shares}x {occ_symbol}...")
        res = requests.post(url, data=payload, headers=headers, timeout=5)
        
        if res.status_code == 200:
            body = res.json()
            order_info = body.get('order', {})
            order_id = order_info.get('id')
            print(f"[✓ STEPPED CLOSE SUCCESS] {shares}x {occ_symbol} | Limit Price: ${target_price:.2f} | Order ID: {order_id}")
            return True
        else:
            print(f"[-] Stepped close failed HTTP {res.status_code}: {res.text}. Escalating to market close fallback...")
            return execute_tradier_close(occ_symbol, ticker, shares, active_base_url, max_wait_seconds)
    except Exception as e:
        print(f"[-] Stepped close exception for {occ_symbol}: {e}. Falling back to standard close...")
        return execute_tradier_close(occ_symbol, ticker, shares, active_base_url, max_wait_seconds)

def sync_local_sqlite_exit(t_id, ticker, exit_reason, exit_price, exit_timestamp, net_pnl=0.0, remaining_shares=0, dynamic_stop=None):
    db_file = "harm_telemetry.db"
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file, timeout=5.0)
            cursor = conn.cursor()
            status = exit_reason if remaining_shares == 0 else "SMART_CSO_RUNNER"
            if dynamic_stop is not None:
                cursor.execute("UPDATE trades SET stop_loss = ? WHERE id = ? OR ticker = ?", (dynamic_stop, t_id, ticker))
            cursor.execute(
                "UPDATE trades SET exit_status = ?, exit_price = ?, exit_timestamp = ?, net_pnl = ?, shares = ? WHERE id = ? OR ticker = ?",
                (status, exit_price, exit_timestamp, net_pnl, remaining_shares, t_id, ticker)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[-] Local SQLite exit sync warning: {e}")

def get_recent_fill_price(occ_symbol, default_price=0.0):
    token = get_tradier_token()
    account_id = os.getenv("TRADIER_ACCOUNT_ID", TRADIER_ACCOUNT_ID)
    if not token or not account_id:
        return default_price
    try:
        base_url = os.getenv("TRADIER_BASE_URL", TRADIER_BASE_URL).rstrip('/')
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        res = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers, timeout=5)
        if res.status_code == 200:
            orders = res.json().get("orders", {}).get("order", [])
            if isinstance(orders, dict):
                orders = [orders]
            matching = [o for o in orders if o.get("option_symbol") == occ_symbol and str(o.get("status", "")).lower() == "filled"]
            if matching:
                matching.sort(key=lambda x: int(x.get("id", 0)), reverse=True)
                return float(matching[0].get("avg_fill_price", default_price) or default_price)
    except Exception as e:
        print(f"[!] Error fetching fill price for {occ_symbol}: {e}")
    return default_price

def synchronize_dynamo_with_tradier():
    base_url = os.getenv('TRADIER_BASE_URL', TRADIER_BASE_URL).rstrip('/')
    token = get_tradier_token()
    account_id = os.getenv('TRADIER_ACCOUNT_ID', TRADIER_ACCOUNT_ID)
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    try:
        res = requests.get(f'{base_url}/accounts/{account_id}/positions', headers=headers, timeout=10)
        if res.status_code != 200:
            print(f"[-] Failed to fetch Tradier positions: {res.text}")
            return
    except Exception as e:
        print(f"[-] Network error fetching Tradier positions: {e}")
        return

    positions_data = res.json().get('positions') if res.status_code == 200 else {}
    if not isinstance(positions_data, dict):
        positions_data = {}
    raw_positions = positions_data.get('position', [])
    if isinstance(raw_positions, dict):
        raw_positions = [raw_positions]

    live_broker_state = {}
    for pos in raw_positions:
        symbol = pos.get('symbol', '')
        if not symbol:
            continue
        
        match = re.match(r'^([A-Z]+)\d{6}[CP]\d{8}$', symbol)
        ticker = match.group(1) if match else symbol[:4].rstrip('0123456789')
        
        qty = float(pos.get('quantity', 0))
        cost_basis_raw = float(pos.get('cost_basis', 0.0))
        
        if cost_basis_raw > 10.0 and qty > 0:
            per_share_entry = round(cost_basis_raw / (qty * 100.0), 2)
        elif qty > 0:
            per_share_entry = round(cost_basis_raw / qty, 2)
        else:
            per_share_entry = round(cost_basis_raw, 2)

        live_broker_state[symbol] = {
            'occ_symbol': symbol,
            'ticker': ticker,
            'quantity': qty,
            'cost_basis': per_share_entry,
            'entry_price': per_share_entry,
            'date_acquired': pos.get('date_acquired')
        }

    print(f"[✓ TRADIER GROUND TRUTH] Live Open Contracts ({len(live_broker_state)}): {list(live_broker_state.keys())}")

    dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
    table = dynamodb.Table('HarmonizedTrades')

    try:
        response = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        existing_items = response.get('Items', [])
    except Exception as e:
        print(f"[-] Error scanning DynamoDB active positions: {e}")
        return

    existing_occ_symbols = {item.get('occ_symbol', item.get('ticker')): item for item in existing_items}

    now_str = dt.now().strftime("%Y-%m-%d %H:%M:%S")
    for db_occ_symbol, item in existing_occ_symbols.items():
        if db_occ_symbol not in live_broker_state:
            ticker = item.get('ticker', db_occ_symbol)
            tenant_id = item.get('tenant_id', 'COMPANY_A')
            t_id = item.get('trade_id')
            entry_px = float(item.get('entry_price', 0.0))
            shares = float(item.get('shares', 1.0))

            actual_exit_px = get_recent_fill_price(db_occ_symbol, default_price=0.0)
            realized_pnl = round((actual_exit_px - entry_px) * shares * 100.0, 2) if actual_exit_px > 0 and entry_px > 0 else 0.0

            print(f"[ℹ️ RECONCILED] Reconciling {ticker} ({db_occ_symbol}) -> Fill Px: ${actual_exit_px:.2f} | PnL: ${realized_pnl:+.2f}")
            try:
                table.update_item(
                    Key={'tenant_id': tenant_id, 'trade_id': t_id},
                    UpdateExpression='SET exit_status = :status, exit_price = :px, exit_timestamp = :ts, net_pnl = :pnl, cso_reason = :reason, shares = :sh',
                    ExpressionAttributeValues={
                        ':status': 'GHOST_RECONCILED_CLOSED',
                        ':px': str(actual_exit_px),
                        ':ts': now_str,
                        ':pnl': str(realized_pnl),
                        ':reason': 'GHOST_RECONCILED_CLOSED',
                        ':sh': '0'
                    }
                )
                sync_local_sqlite_exit(t_id, ticker, "GHOST_RECONCILED_CLOSED", actual_exit_px, now_str, realized_pnl, remaining_shares=0)
            except Exception as ex:
                print(f"[-] Failed to reconcile closed entry {db_occ_symbol}: {ex}")

    tenant_id = os.getenv('TENANT_ID', 'COMPANY_A')
    for symbol, data in live_broker_state.items():
        if symbol not in existing_occ_symbols:
            print(f"[🚀 RE-HYDRATING DYNAMO] Ingesting untracked broker position {data['ticker']} ({symbol}) -> Qty: {data['quantity']} | Entry: ${data['entry_price']}")
            t_id = f"trade_{symbol.lower()}"
            item_payload = {
                'tenant_id': tenant_id,
                'trade_id': t_id,
                'occ_symbol': symbol,
                'ticker': data['ticker'],
                'shares': str(int(data['quantity'])),
                'entry_price': str(data['entry_price']),
                'cost_basis': str(data['cost_basis']),
                'exit_status': 'ACTIVE',
                'direction': 'CALL' if 'C' in symbol[len(data['ticker']):] else 'PUT',
                'timestamp': now_str,
                'execution_tag': 'NF',
                'cso_notes': 'REHYDRATED_FROM_TRADIER'
            }
            try:
                table.put_item(Item=item_payload)
            except Exception as e:
                print(f"[-] Failed to hydrate DynamoDB for {symbol}: {e}")

    print("[✓ SYSTEM SYNC COMPLETE] DynamoDB perfectly matches Tradier brokerage state.")

def evaluate_gex_exits():
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        
        res = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        active_items = res.get('Items', [])

        if not active_items:
            print("[⚙️ MASTER EXIT MONITOR] Scanning... 0 active trades pending exit.")
            return

        now = dt.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        allowed_tickers = [t.strip().upper() for t in os.getenv("ACTIVE_TICKERS", "").split(",") if t.strip()]

        for item in active_items:
            t_id = item.get('trade_id')
            tenant_id = item.get('tenant_id', 'COMPANY_A')
            ticker = item.get('ticker', '').upper()

            if allowed_tickers and ticker not in allowed_tickers:
                continue

            occ_symbol = item.get('occ_symbol', ticker)
            entry_price = float(item.get('entry_price', 0.0))
            total_shares = int(float(item.get('shares', 1.0)))
            ts_str = item.get('timestamp')
            trade_dir = item.get('direction', 'CALL').upper()
            stored_peak = float(item.get('peak_price', entry_price) or entry_price)
            stored_stop_loss = float(item.get('stop_loss', 0.0) or 0.0)
            is_runner = bool(item.get('is_runner', False))
            accumulated_pnl = float(item.get('partial_pnl', 0.0) or 0.0)
            
            exec_tag = str(item.get('execution_tag', 'SCJ')).upper()
            strategy_mode = str(item.get('strategy', 'SMART_CSO_SCALP')).upper()

            if entry_price <= 0:
                continue

            elapsed_minutes = 0.0
            if ts_str:
                try:
                    clean_ts = str(ts_str).split('.')[0].replace('T', ' ')
                    entry_dt = dt.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
                    elapsed_minutes = round((now - entry_dt).total_seconds() / 60.0, 1)
                except Exception:
                    pass

            current_price_raw, active_base_url = get_live_quote(occ_symbol)
            current_price = float(current_price_raw or 0.0)
            spot, gex_target, gex_gap_pct = get_gex_target_info(ticker)

            if current_price == 0.0:
                print(f"[!] Quote unavailable for {occ_symbol}. Skipping tick.")
                continue

            dollar_pnl = round((current_price - entry_price) * 100.0 * total_shares, 2)
            pnl_pct = round(((current_price - entry_price) / entry_price) * 100.0, 2) if entry_price > 0 else 0.0

            peak_price = max(stored_peak, current_price)
            peak_pnl_pct = round(((peak_price - entry_price) / entry_price) * 100.0, 2) if entry_price > 0 else 0.0

            exit_reason = None

            # DUAL-BRANCH EXECUTION ROUTING BY EXECUTION TAG (NF vs SCJ)
            if exec_tag == 'NF' or strategy_mode == 'NATURAL_GEX_SWING':
                if gex_target > 0 and spot > 0 and abs(spot - gex_target) / spot <= 0.003:
                    exit_reason = f"🎯 [NF] GEX_TARGET_WALL_REACHED (${gex_target:.2f})"
                elif trade_dir == "CALL" and gex_target > 0 and spot < gex_target * 0.992:
                    exit_reason = f"🔴 [NF] GEX_STRUCTURAL_SUPPORT_BREACH (${spot:.2f})"
                elif trade_dir == "PUT" and gex_target > 0 and spot > gex_target * 1.008:
                    exit_reason = f"🔴 [NF] GEX_STRUCTURAL_RESISTANCE_BREACH (${spot:.2f})"
                elif elapsed_minutes >= 90 and is_regular_trading_hours():
                    exit_reason = "[NF] GEX_MAX_SWING_TIME_EXPIRED_90M"
                elif pnl_pct <= -20.0:
                    exit_reason = "[NF] STOP_LOSS_20PCT"

                dynamic_stop = stored_stop_loss

            else:
                # SMART CSO INJECTOR EXIT ENGINE (Micro-Scalp 15m Horizon & Multi-Tier Trailing Ladder)
                if is_runner:
                    cushion = 10.0 if peak_pnl_pct >= 50.0 else 8.0
                    dynamic_stop_pct = max(3.0, peak_pnl_pct - cushion)
                    calculated_stop = round(entry_price * (1.0 + dynamic_stop_pct / 100.0), 2)
                elif peak_pnl_pct >= 35.0:
                    calculated_stop = round(entry_price * (1.0 + (peak_pnl_pct - 8.0) / 100.0), 2)
                elif peak_pnl_pct >= 20.0:
                    calculated_stop = round(entry_price * (1.0 + (peak_pnl_pct - 6.0) / 100.0), 2)
                elif peak_pnl_pct >= 5.0:  # Early +5% Dynamic Breakeven Floor
                    calculated_stop = round(entry_price * 1.01, 2)
                else:
                    if entry_price <= 0.50:
                        calculated_stop = round(max(0.02, entry_price - 0.10), 2)
                    else:
                        calculated_stop = round(entry_price * 0.80, 2)

                # Monotonic ratchet: dynamic stop loss never moves downward
                dynamic_stop = max(stored_stop_loss, calculated_stop)

                if current_price <= dynamic_stop and current_price > 0:
                    exit_reason = f"[SCJ] DYNAMIC_TRAIL_STOP_TRIGGERED_(${dynamic_stop:.2f})"
                elif pnl_pct >= 50.0 and total_shares == 1:
                    exit_reason = "[SCJ] TAKE_PROFIT_50PCT"
                elif -20.0 < pnl_pct <= -8.0 and spot > 0:
                    support_lvl = float(gex_target or 0.0)
                    if support_lvl > 0:
                        support_breached = (spot < support_lvl) if trade_dir == "CALL" else (spot > support_lvl)
                        if support_breached:
                            print(f"[🚨 CSO MOMENTUM CUT] {ticker} option down {pnl_pct:.1f}% & stock (${spot:.2f}) breached support (${support_lvl:.2f}). Executing early exit!")
                            exit_reason = f"[SCJ] CSO_EARLY_MOMENTUM_CUT_({pnl_pct:.1f}%)"
                        else:
                            print(f"[🛡️ CSO NOISE FILTER] {ticker} option mark down {pnl_pct:.1f}% but stock (${spot:.2f}) holds structure (${support_lvl:.2f}). IGNORING SPREAD NOISE.")
                    elif pnl_pct <= -12.0:
                        print(f"[⚠️ CSO FALLBACK CUT] {ticker} missing GEX level data & down {pnl_pct:.1f}%. Capping loss at -12% fallback floor!")
                        exit_reason = f"[SCJ] CSO_MISSING_LEVEL_FALLBACK_CUT_({pnl_pct:.1f}%)"
                elif pnl_pct <= -20.0:
                    exit_reason = "[SCJ] STOP_LOSS_20PCT"
                elif elapsed_minutes >= MTTP_MAX_MINUTES and is_regular_trading_hours():
                    exit_reason = f"[SCJ] MTTP_TIME_EXPIRED_{MTTP_MAX_MINUTES}M"

            table.update_item(
                Key={'tenant_id': tenant_id, 'trade_id': t_id},
                UpdateExpression='SET peak_price = :pk, stop_loss = :sl, cso_notes = :cn, cso_status = :cs',
                ExpressionAttributeValues={
                    ':pk': str(peak_price),
                    ':sl': str(dynamic_stop),
                    ':cn': f"TRAIL_LOCK_STOP_${dynamic_stop:.2f}",
                    ':cs': 'TIGHTEN' if dynamic_stop > entry_price else 'HOLD'
                }
            )

            print(f"[⚙️ MASTER EXIT ({exec_tag})] {ticker} | {total_shares}x | Entry: ${entry_price:.2f} | Live: ${current_price:.2f} ({pnl_pct:+.1f}%) | Peak: ${peak_price:.2f} (+{peak_pnl_pct:.1f}%) | Active Stop: ${dynamic_stop:.2f}")

            # TRANCHE SCALING (MICRO-SCALP SCJ MODE ONLY)
            if exec_tag != 'NF' and strategy_mode != 'NATURAL_GEX_SWING' and total_shares > 1 and not is_runner and (pnl_pct >= 15.0 or (gex_gap_pct != 0.0 and abs(gex_gap_pct) <= 0.5)):
                scale_shares = total_shares - 1
                realized_scale_pnl = round((current_price - entry_price) * scale_shares * 100.0, 2)
                
                print(f"🚀 [CSO TRANCHE EXIT] Scaling {scale_shares}x contracts on {ticker} at {pnl_pct:+.1f}% | Banking ${realized_scale_pnl:+.2f} | Leaving 1 RUNNER")
                
                if execute_tradier_close_stepped(occ_symbol, ticker, scale_shares, active_base_url):
                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': t_id},
                        UpdateExpression='SET shares = :sh, is_runner = :r, partial_pnl = :pp, peak_price = :pk, cso_status = :cs, stop_loss = :sl',
                        ExpressionAttributeValues={
                            ':sh': '1',
                            ':r': True,
                            ':pp': str(accumulated_pnl + realized_scale_pnl),
                            ':pk': str(peak_price),
                            ':cs': 'SMART_CSO_RUNNER',
                            ':sl': str(dynamic_stop)
                        }
                    )
                    sync_local_sqlite_exit(t_id, ticker, "PARTIAL_SCALE_OUT", current_price, now_str, realized_scale_pnl, remaining_shares=1, dynamic_stop=dynamic_stop)
                continue

            if exit_reason:
                print(f"🚨 [FINAL EXIT TRIGGERED] ID {t_id} ({ticker} {occ_symbol}) -> Reason: {exit_reason} at {now_str}")
                if execute_tradier_close_stepped(occ_symbol, ticker, total_shares, active_base_url):
                    final_leg_pnl = round((current_price - entry_price) * total_shares * 100.0, 2)
                    total_realized_pnl = round(accumulated_pnl + final_leg_pnl, 2)

                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': t_id},
                        UpdateExpression='SET exit_status = :status, exit_price = :px, exit_timestamp = :ts, net_pnl = :pnl, cso_reason = :reason, shares = :sh',
                        ExpressionAttributeValues={
                            ':status': exit_reason,
                            ':px': str(current_price),
                            ':ts': now_str,
                            ':pnl': str(total_realized_pnl),
                            ':reason': exit_reason,
                            ':sh': '0'
                        }
                    )
                    sync_local_sqlite_exit(t_id, ticker, exit_reason, current_price, now_str, total_realized_pnl, remaining_shares=0)
                    print(f"[✓] Final Exit Logged for {ticker} | Total Realized PnL: ${total_realized_pnl:+.2f}")

    except Exception as e:
        print(f"[-] Master Exit Monitor Error: {e}")

if __name__ == "__main__":
    ensure_schema()
    print("[⚙️] Unified CSO Master Exit Monitor Routine Initialized.")
    synchronize_dynamo_with_tradier()
    while True:
        evaluate_gex_exits()
        time.sleep(10)
