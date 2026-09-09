import os, sys

if os.getenv('EXECUTION_ENV', '').upper() == 'SANDBOX':
    os.environ['TRADIER_BASE_URL'] = 'https://sandbox.tradier.com/v1'
    if os.getenv('TRADIER_SANDBOX_TOKEN'):
        os.environ['TRADIER_TOKEN'] = os.getenv('TRADIER_SANDBOX_TOKEN')

# ==============================================================================
# HARM.AI OPTIMIZED CHIEF STRATEGY OFFICER (CSO) MASTER EXIT MONITOR (AUTO-DISCOVERY)
# WITH 2-CYCLE PERSISTENCE DEBOUNCE CONFIRMATION
# ==============================================================================
import time
import json
import sqlite3
import requests
import boto3
import datetime
from datetime import datetime as dt, timezone
import pytz
import re
from pathlib import Path
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr

# Inbound broker ground-truth reconciliation hook
try:
    from src.broker_reconciliation import reconcile_broker_state
except ImportError:
    try:
        from broker_reconciliation import reconcile_broker_state
    except ImportError:
        reconcile_broker_state = None

if os.path.exists('.env.prod'):
    load_dotenv('.env.prod', override=True)
else:
    load_dotenv(override=True)

MANIFEST_PATH = "trading_levels.json"
MTTP_MAX_MINUTES = int(os.getenv("MTTP_MAX_MINUTES", 25))  # Expanded horizon to let runners develop
DB_FILE = "harm_telemetry.db"

# In-memory deduplication and execution lock trackers
ADOPTED_SYMBOLS = set()
PENDING_CLOSE_SYMBOLS = set()
ACTIVE_BROKER_STOPS = {}  # {occ_symbol: {"order_id": id, "stop_price": px, "placed_at": epoch}}

# Debounce tracking: {occ_symbol: {"breach_count": int, "first_breach_time": float, "breached_price": float}}
BREACH_WARNING_CYCLES = {}

def get_tenant_id():
    explicit = os.getenv('TENANT_ID')
    if explicit:
        return explicit
    exec_env = os.getenv('EXECUTION_ENV', 'SANDBOX').upper()
    if exec_env in ['PROD', 'PRODUCTION', 'LIVE']:
        return 'COMPANY_A_PROD'
    return 'COMPANY_A_SANDBOX'

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
    now = dt.now(ny_tz)
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
    db_file = DB_FILE
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            for col in [
                "exit_timestamp TEXT", 
                "peak_price REAL", 
                "is_runner INTEGER", 
                "partial_pnl REAL", 
                "min_pnl_seen REAL", 
                "execution_tag TEXT DEFAULT 'SCJ'", 
                "occ_symbol TEXT", 
                "partial_taken BOOLEAN DEFAULT 0"
            ]:
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

def has_active_broker_stop(occ_symbol, account_id, active_base_url, headers):
    now = time.time()
    if occ_symbol in ACTIVE_BROKER_STOPS:
        cached = ACTIVE_BROKER_STOPS[occ_symbol]
        if now - cached.get("placed_at", 0) < 180:
            return True

    try:
        url = f"{active_base_url}/accounts/{account_id}/orders"
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            orders_data = res.json().get('orders', {}).get('order', [])
            if isinstance(orders_data, dict):
                orders_data = [orders_data]
            for od in orders_data:
                if (od.get('option_symbol') == occ_symbol 
                    and od.get('status') in ['open', 'pending'] 
                    and od.get('side') == 'sell_to_close'):
                    ACTIVE_BROKER_STOPS[occ_symbol] = {
                        "order_id": od.get('id'),
                        "stop_price": float(od.get('stop_price') or 0.0),
                        "placed_at": now
                    }
                    return True
    except Exception:
        pass
    return False

def cancel_resting_broker_orders(occ_symbol, account_id, active_base_url, headers):
    cancelled_any = False
    if occ_symbol in ACTIVE_BROKER_STOPS:
        cached_stop_id = ACTIVE_BROKER_STOPS[occ_symbol].get("order_id")
        if cached_stop_id:
            try:
                requests.delete(f"{active_base_url}/accounts/{account_id}/orders/{cached_stop_id}", headers=headers, timeout=3)
                cancelled_any = True
            except Exception:
                pass
        del ACTIVE_BROKER_STOPS[occ_symbol]

    try:
        url = f"{active_base_url}/accounts/{account_id}/orders"
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            orders_data = res.json().get('orders', {}).get('order', [])
            if isinstance(orders_data, dict):
                orders_data = [orders_data]
            for od in orders_data:
                if (od.get('option_symbol') == occ_symbol 
                    and od.get('status') in ['open', 'pending'] 
                    and od.get('side') == 'sell_to_close'):
                    od_id = od.get('id')
                    try:
                        requests.delete(f"{active_base_url}/accounts/{account_id}/orders/{od_id}", headers=headers, timeout=3)
                        cancelled_any = True
                    except Exception:
                        pass
    except Exception:
        pass

    if cancelled_any:
        time.sleep(0.5)

def execute_tradier_close(occ_symbol, ticker, shares, base_url=None, max_wait_seconds=10):
    token = get_tradier_token()
    account_id = os.getenv("TRADIER_ACCOUNT_ID", TRADIER_ACCOUNT_ID)
    active_base_url = (base_url or os.getenv("TRADIER_BASE_URL", TRADIER_BASE_URL)).rstrip('/')

    if not token or not account_id:
        return False

    match = re.match(r'^([A-Z]+)\d{6}[CP]\d{8}$', occ_symbol)
    root_symbol = match.group(1) if match else ticker

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    payload = {
        'class': 'option', 'symbol': root_symbol, 'option_symbol': occ_symbol,
        'side': 'sell_to_close', 'quantity': str(abs(int(shares))), 'type': 'market', 'duration': 'day'
    }

    try:
        url = f"{active_base_url}/accounts/{account_id}/orders"
        res = requests.post(url, data=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            return True
    except Exception:
        pass
    return False

def execute_tradier_close_stepped(occ_symbol, ticker, shares, base_url=None, max_wait_seconds=10):
    token = get_tradier_token()
    account_id = os.getenv("TRADIER_ACCOUNT_ID", TRADIER_ACCOUNT_ID)
    active_base_url = (base_url or os.getenv("TRADIER_BASE_URL", TRADIER_BASE_URL)).rstrip('/')

    if not token or not account_id:
        return True

    bid, ask, _ = get_live_bid_ask(occ_symbol)
    mid = round((bid + ask) / 2.0, 2) if (bid > 0 and ask > 0) else 0.0
    target_price = max(mid, bid, 0.01)

    match = re.match(r'^([A-Z]+)\d{6}[CP]\d{8}$', occ_symbol)
    root_symbol = match.group(1) if match else ticker

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    payload = {
        "class": "option", "symbol": root_symbol, "option_symbol": occ_symbol,
        "side": "sell_to_close", "quantity": str(abs(int(shares))), "type": "limit", "price": f"{target_price:.2f}", "duration": "day"
    }

    try:
        url = f"{active_base_url}/accounts/{account_id}/orders"
        res = requests.post(url, data=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            body = res.json()
            order_info = body.get('order', {})
            order_id = order_info.get('id') if isinstance(order_info, dict) else None
            print(f"[✓ STEPPED CLOSE SUCCESS] {shares}x {occ_symbol} | Limit Price: ${target_price:.2f} | Order ID: {order_id}")
            return True
        else:
            return execute_tradier_close(occ_symbol, ticker, shares, active_base_url, max_wait_seconds)
    except Exception:
        return execute_tradier_close(occ_symbol, ticker, shares, active_base_url, max_wait_seconds)

def place_broker_stop_order(occ_symbol, ticker, shares, stop_price, base_url=None):
    token = get_tradier_token()
    account_id = os.getenv("TRADIER_ACCOUNT_ID", TRADIER_ACCOUNT_ID)
    active_base_url = (base_url or os.getenv("TRADIER_BASE_URL", TRADIER_BASE_URL)).rstrip('/')

    if not token or not account_id:
        return False

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    if has_active_broker_stop(occ_symbol, account_id, active_base_url, headers):
        return True

    match = re.match(r'^([A-Z]+)\d{6}[CP]\d{8}$', occ_symbol)
    root_symbol = match.group(1) if match else ticker

    payload = {
        "class": "option", "symbol": root_symbol, "option_symbol": occ_symbol,
        "side": "sell_to_close", "quantity": str(abs(int(shares))),
        "type": "stop", "stop": f"{stop_price:.2f}", "duration": "day"
    }

    try:
        url = f"{active_base_url}/accounts/{account_id}/orders"
        res = requests.post(url, data=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            body = res.json()
            order_info = body.get('order', {})
            order_id = order_info.get('id') if isinstance(order_info, dict) else None
            ACTIVE_BROKER_STOPS[occ_symbol] = {
                "order_id": order_id,
                "stop_price": stop_price,
                "placed_at": time.time()
            }
            print(f"[🛡️ BROKER STOP PLACED] {shares}x {occ_symbol} @ Stop ${stop_price:.2f} | Order ID: {order_id}")
            return True
    except Exception as e:
        print(f"[-] Error placing broker stop order for {occ_symbol}: {e}")
    return False

def sync_local_sqlite_exit(t_id, ticker, exit_reason, exit_price, exit_timestamp, net_pnl=0.0, remaining_shares=0, dynamic_stop=None):
    if os.path.exists(DB_FILE):
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5.0)
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
        except Exception:
            pass

def sync_sqlite_to_dynamo():
    try:
        if not os.path.exists(DB_FILE):
            return
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        tenant_id = get_tenant_id()

        conn = sqlite3.connect(DB_FILE, timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE exit_status = 'ACTIVE'")
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            row_id = str(row["id"])
            t_id = f"trade_local_{row_id}"
            ticker = row["ticker"]
            occ = row["occ_symbol"] if "occ_symbol" in row.keys() and row["occ_symbol"] else ticker
            entry_p = float(row["entry_price"] or row["spot_price"] or 0.0)
            shares = str(row["shares"] or "1")
            direction = row["direction"] or "CALL"
            timestamp = row["timestamp"]
            
            # Proportional stop scaling respecting 35% hard stop rule for sub-$1.00 options
            if entry_p <= 1.00:
                calc_stop = round(max(0.10, entry_p * 0.65), 2)  # Max 35% drawdown limit
            else:
                calc_stop = round(entry_p * 0.70, 2)
            
            stop_loss = str(row["stop_loss"] or round(calc_stop, 2))
            take_profit = str(row["take_profit"] or round(entry_p * 1.50, 2))

            item_payload = {
                'tenant_id': tenant_id, 'trade_id': t_id, 'occ_symbol': occ, 'ticker': ticker,
                'shares': shares, 'entry_price': str(entry_p), 'stop_loss': stop_loss, 'take_profit': take_profit,
                'exit_status': 'ACTIVE', 'direction': direction, 'timestamp': timestamp,
                'execution_env': os.getenv('EXECUTION_ENV', 'SANDBOX'), 'is_live': int(os.getenv('IS_LIVE', 0)),
                'strategy': str(row["strategy"] if "strategy" in row.keys() else "SMART_CSO_SCALP")
            }
            table.put_item(Item=item_payload)
    except Exception as e:
        print(f"[-] SQLite to Dynamo sync warning: {e}")

def evaluate_gex_exits():
    if reconcile_broker_state:
        try:
            reconcile_broker_state()
        except Exception as _re_ex:
            print(f"[-] Broker reconciliation warning: {_re_ex}")

    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        tenant_id = get_tenant_id()
        
        res = table.scan(FilterExpression=Attr('tenant_id').eq(tenant_id) & Attr('exit_status').eq('ACTIVE'))
        active_items = res.get('Items', [])

        if not active_items:
            print(f"[⚙️ MASTER EXIT MONITOR] Scanning DynamoDB ({tenant_id})... 0 active trades pending exit.")
            return

        now = dt.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n=======================================================================================================================")
        print(f"📊 AUTO-DISCOVERED CSO MASTER MONITOR | {len(active_items)} ACTIVE TRADES ({tenant_id}) | {now_str}")
        print(f"=======================================================================================================================")
        print(f"{'SYMBOL':<20} | {'DIR':<5} | {'ENTRY':<8} | {'MARK':<8} | {'SHARES':<6} | {'STOP':<8} | {'MTTP / HORIZON':<15} | {'PNL':<10}")
        print(f"-" * 105)

        for item in active_items:
            t_id = item.get('trade_id')
            ticker = str(item.get('ticker', '')).upper()
            occ_symbol = str(item.get('occ_symbol', ticker))
            
            if occ_symbol in PENDING_CLOSE_SYMBOLS:
                continue

            entry_price = float(item.get('entry_price', 0.0) or 0.0)
            
            raw_shares = item.get('shares')
            if raw_shares is None or str(raw_shares).lower() in ['none', '']:
                total_shares = 1
            else:
                try:
                    total_shares = int(float(raw_shares))
                except Exception:
                    total_shares = 1

            trade_dir = str(item.get('direction', 'CALL')).upper()
            stored_peak = float(item.get('peak_price', entry_price) or entry_price)
            accumulated_pnl = float(item.get('partial_pnl', 0.0) or 0.0)
            ts_str = item.get('timestamp')

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
            if current_price == 0.0:
                current_price = entry_price

            peak_price = max(stored_peak, current_price)
            pnl_pct = round(((current_price - entry_price) / entry_price) * 100.0, 2)
            peak_pnl_pct = round(((peak_price - entry_price) / entry_price) * 100.0, 2)

            # Proportional stop scaling respecting 35% hard stop rule for sub-$1.00 options
            if entry_price <= 1.00:
                base_stop = round(max(0.10, entry_price * 0.65), 2)
            else:
                base_stop = round(entry_price * 0.70, 2)

            existing_sl = float(item.get('stop_loss', 0.0) or 0.0)

            # --- DYNAMIC STOP WITH PEAK-DRAWDOWN BUFFER ---
            if elapsed_minutes < 3.0:
                dynamic_stop = base_stop
            else:
                if peak_pnl_pct >= 40.0:
                    target_stop = round(entry_price * 1.25, 2)
                elif peak_pnl_pct >= 30.0:
                    target_stop = round(entry_price * 1.15, 2)
                elif peak_pnl_pct >= 20.0:
                    target_stop = round(entry_price * 1.08, 2)
                elif peak_pnl_pct >= 15.0:
                    target_stop = round(entry_price * 1.00, 2)
                else:
                    target_stop = base_stop
                dynamic_stop = max(base_stop, target_stop, existing_sl)

            mttp_status = f"{elapsed_minutes:.1f}m / {MTTP_MAX_MINUTES}m"

            print(f"{occ_symbol:<20} | {trade_dir:<5} | ${entry_price:<7.2f} | ${current_price:<7.2f} | {total_shares:<6} |${dynamic_stop:<7.2f} | {mttp_status:<15} | {pnl_pct:+6.1f}%")

            exit_reason = None

            spot_price, _, _ = get_gex_target_info(ticker)
            vwap = float(item.get('entry_vwap', spot_price) or spot_price)
            
            # Suppress thesis failure during the first 5 minutes
            if spot_price > 0 and vwap > 0 and elapsed_minutes >= 5.0:
                if trade_dir == "CALL" and spot_price < (vwap * 0.9970):
                    exit_reason = "[TRADEALGO] THESIS_FAILED_VWAP_BREAK_DOWN"
                elif trade_dir == "PUT" and spot_price > (vwap * 1.0030):
                    exit_reason = "[TRADEALGO] THESIS_FAILED_VWAP_RECLAIMED"
            
            if not exit_reason:
                # --- OPTIMIZED PEAK-DRAWDOWN TRAILING STOP GUARD ---
                drawdown_from_peak_pct = round(((peak_price - current_price) / peak_price) * 100.0, 2) if peak_price > 0 else 0.0

                if peak_pnl_pct >= 50.0:
                    allowable_drawdown = 30.0
                elif peak_pnl_pct >= 30.0:
                    allowable_drawdown = 25.0
                elif peak_pnl_pct >= 15.0:
                    allowable_drawdown = 20.0
                else:
                    allowable_drawdown = 15.0

                # 1. Hard Emergency Stops (NO DEBOUNCE - Immediate Execution)
                if pnl_pct <= -35.0:
                    exit_reason = "[SCJ] EMERGENCY_STOP_35PCT_BREACH"
                    BREACH_WARNING_CYCLES.pop(occ_symbol, None)
                elif pnl_pct >= 50.0 and total_shares == 1:
                    exit_reason = "[SCJ] TAKE_PROFIT_50PCT"
                    BREACH_WARNING_CYCLES.pop(occ_symbol, None)
                elif elapsed_minutes >= MTTP_MAX_MINUTES and is_regular_trading_hours():
                    if pnl_pct > 15.0:
                        pass  # Let strong winning trends run
                    elif pnl_pct > 0:
                        exit_reason = f"[MTTP] TIME_HORIZON_EXPIRED_SECURED_+{pnl_pct}%"
                    else:
                        exit_reason = f"[MTTP] TIME_EXPIRED_STALLED_MOMENTUM"
                    BREACH_WARNING_CYCLES.pop(occ_symbol, None)

                # 2. Dynamic Trailing Stop (DEBOUNCED - Requires 2 Consecutive Cycles)
                elif current_price <= dynamic_stop and current_price > 0:
                    if peak_pnl_pct >= 20.0 and drawdown_from_peak_pct < allowable_drawdown:
                        # Allow consolidation retracement without choking out the runner
                        BREACH_WARNING_CYCLES.pop(occ_symbol, None)
                    elif elapsed_minutes < 5.0 and pnl_pct > -25.0:
                        # Let young trades breathe
                        BREACH_WARNING_CYCLES.pop(occ_symbol, None)
                    else:
                        # Soft trailing stop breach - evaluate debounce
                        warn_state = BREACH_WARNING_CYCLES.get(occ_symbol)
                        if not warn_state:
                            # Cycle 1: Set warning, do NOT execute
                            BREACH_WARNING_CYCLES[occ_symbol] = {
                                "breach_count": 1,
                                "first_time": time.time(),
                                "price": current_price
                            }
                            print(f"  ⚠️ [STOP WARNING 1/2] {occ_symbol} mark ${current_price:.2f} <= stop ${dynamic_stop:.2f}. Holding for confirmation cycle...")
                        else:
                            # Cycle 2: Breach confirmed across consecutive polling loops -> Fire Exit
                            if peak_pnl_pct >= 15.0:
                                exit_reason = f"[MTTP] PEAK_DRAWDOWN_TRAIL_CONFIRMED_(${dynamic_stop:.2f})_[Peak:+{peak_pnl_pct}%_DD:-{drawdown_from_peak_pct}%]"
                            else:
                                exit_reason = f"[SCJ] DYNAMIC_TRAIL_STOP_CONFIRMED_(${dynamic_stop:.2f})"
                            BREACH_WARNING_CYCLES.pop(occ_symbol, None)
                            print(f"  🛑 [CONFIRMED 2-CYCLE EXIT] {occ_symbol} sustained breach below ${dynamic_stop:.2f}. Triggering order!")
                else:
                    # Price is above dynamic stop: Clear pending warning if price recovered
                    if occ_symbol in BREACH_WARNING_CYCLES:
                        print(f"  🛡️ [DEBOUNCE FILTERED] {occ_symbol} recovered to ${current_price:.2f} (above stop ${dynamic_stop:.2f}). Spurious wick rejected!")
                        BREACH_WARNING_CYCLES.pop(occ_symbol, None)

            table.update_item(
                Key={'tenant_id': tenant_id, 'trade_id': t_id},
                UpdateExpression='SET peak_price = :pk, stop_loss = :sl, cso_notes = :cn',
                ExpressionAttributeValues={
                    ':pk': str(peak_price), ':sl': str(dynamic_stop), ':cn': f"TRAIL_LOCK_STOP_${dynamic_stop:.2f}"
                }
            )

            if peak_pnl_pct >= 15.0 and stored_peak < peak_price:
                place_broker_stop_order(occ_symbol, ticker, total_shares, dynamic_stop, active_base_url)

            # Partial Scaling: 50% Scale-Out at +20% PnL
            is_partial_taken = item.get('partial_taken', False)
            if not is_partial_taken and total_shares >= 2 and pnl_pct >= 20.0:
                half_shares = total_shares // 2
                print(f"⚖️ [PARTIAL SCALING TRIGGERED] {ticker} ({occ_symbol}) hit +{pnl_pct}%. Scaling out {half_shares}x shares (50% position)...")
                token = get_tradier_token()
                headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
                if execute_tradier_close_stepped(occ_symbol, ticker, half_shares, active_base_url):
                    partial_realized = round((current_price - entry_price) * half_shares * 100.0, 2)
                    remaining_shares = total_shares - half_shares
                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': t_id},
                        UpdateExpression='SET shares = :sh, partial_pnl = :pp, partial_taken = :pt',
                        ExpressionAttributeValues={
                            ':sh': str(remaining_shares), ':pp': str(partial_realized), ':pt': True
                        }
                    )
                    sync_local_sqlite_exit(t_id, ticker, "PARTIAL_SCALE_20PCT", current_price, now_str, partial_realized, remaining_shares=remaining_shares, dynamic_stop=dynamic_stop)
                    print(f"[✓ PARTIAL SCALE SUCCESS] Locked ${partial_realized:+.2f} profit. Remaining runner shares: {remaining_shares}")
                    continue

            # Execute full exit if reason was set and confirmed
            if exit_reason:
                PENDING_CLOSE_SYMBOLS.add(occ_symbol)
                print(f"🚨 [EXIT TRIGGERED] {ticker} ({occ_symbol}) -> {exit_reason}")

                token = get_tradier_token()
                headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
                cancel_resting_broker_orders(occ_symbol, os.getenv("TRADIER_ACCOUNT_ID", TRADIER_ACCOUNT_ID), active_base_url, headers)
                
                close_success = execute_tradier_close_stepped(occ_symbol, ticker, total_shares, active_base_url)
                if close_success:
                    final_pnl = round((current_price - entry_price) * total_shares * 100.0, 2)
                    total_net = round(accumulated_pnl + final_pnl, 2)
                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': t_id},
                        UpdateExpression='SET exit_status = :status, exit_price = :px, exit_timestamp = :ts, net_pnl = :pnl, shares = :sh',
                        ExpressionAttributeValues={
                            ':status': exit_reason, ':px': str(current_price), ':ts': now_str, ':pnl': str(total_net), ':sh': '0'
                        }
                    )
                    sync_local_sqlite_exit(t_id, ticker, exit_reason, current_price, now_str, total_net, remaining_shares=0)
                    ADOPTED_SYMBOLS.add(occ_symbol)
                    print(f"[✓] Position Closed Successfully | Net PnL: ${total_net:+.2f}")
                else:
                    print(f"[!] Close order failed for {occ_symbol}. Releasing PENDING_CLOSE lock to allow retry.")
                    PENDING_CLOSE_SYMBOLS.discard(occ_symbol)

    except Exception as e:
        print(f"[-] Master Exit Monitor Error: {e}")

if __name__ == "__main__":
    ensure_schema()
    print("[⚙️] Auto-Discovering Master Exit Monitor Initialized (2-Cycle Debounce Active).")
    sync_sqlite_to_dynamo()
    print("[🚀 ENTERING ACTIVE MASTER EXIT MONITOR LOOP...]")
    while True:
        try:
            evaluate_gex_exits()
            write_heartbeat("GexExitMonitor")
        except Exception as e:
            print(f"[-] Loop error: {e}")
        time.sleep(2.5)
