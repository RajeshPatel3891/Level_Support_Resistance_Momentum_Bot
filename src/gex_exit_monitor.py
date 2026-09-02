import os, sys

if os.getenv('EXECUTION_ENV', '').upper() == 'SANDBOX':
    os.environ['TRADIER_BASE_URL'] = 'https://sandbox.tradier.com/v1'
    if os.getenv('TRADIER_SANDBOX_TOKEN'):
        os.environ['TRADIER_TOKEN'] = os.getenv('TRADIER_SANDBOX_TOKEN')

# ==============================================================================
# HARM.AI OPTIMIZED CHIEF STRATEGY OFFICER (CSO) MASTER EXIT MONITOR (AUTO-DISCOVERY)
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
DB_FILE = "harm_telemetry.db"

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
    db_file = DB_FILE
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            for col in ["exit_timestamp TEXT", "peak_price REAL", "is_runner INTEGER", "partial_pnl REAL", "min_pnl_seen REAL", "execution_tag TEXT DEFAULT 'SCJ'", "occ_symbol TEXT"]:
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
        tenant_id = os.getenv('TENANT_ID', 'COMPANY_A')

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
            stop_loss = str(row["stop_loss"] or round(entry_p * 0.80, 2))
            take_profit = str(row["take_profit"] or round(entry_p * 1.50, 2))

            item_payload = {
                'tenant_id': tenant_id, 'trade_id': t_id, 'occ_symbol': occ, 'ticker': ticker,
                'shares': shares, 'entry_price': str(entry_p), 'stop_loss': stop_loss, 'take_profit': take_profit,
                'exit_status': 'ACTIVE', 'direction': direction, 'timestamp': timestamp,
                'execution_env': 'SANDBOX', 'is_live': 0, 'strategy': str(row["strategy"] if "strategy" in row.keys() else "SMART_CSO_SCALP")
            }
            table.put_item(Item=item_payload)
    except Exception:
        pass

def synchronize_dynamo_with_tradier():
    base_url = os.getenv('TRADIER_BASE_URL', TRADIER_BASE_URL).rstrip('/')
    token = get_tradier_token()
    account_id = os.getenv('TRADIER_ACCOUNT_ID', TRADIER_ACCOUNT_ID)
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    try:
        res = requests.get(f'{base_url}/accounts/{account_id}/positions', headers=headers, timeout=10)
        if res.status_code != 200:
            return
    except Exception:
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

    dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
    table = dynamodb.Table('HarmonizedTrades')

    try:
        response = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        existing_items = response.get('Items', [])
    except Exception:
        return

    existing_occ_symbols = {item.get('occ_symbol', item.get('ticker')): item for item in existing_items}
    now_str = dt.now().strftime("%Y-%m-%d %H:%M:%S")

    tenant_id = os.getenv('TENANT_ID', 'COMPANY_A')
    for symbol, data in live_broker_state.items():
        if symbol not in existing_occ_symbols:
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
            except Exception:
                pass

def evaluate_gex_exits():
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
         
        res = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        active_items = res.get('Items', [])

        if not active_items:
            print("[⚙️ MASTER EXIT MONITOR] Scanning DynamoDB... 0 active trades pending exit.")
            return

        now = dt.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        print(f"\n=======================================================================================================================")
        print(f"📊 AUTO-DISCOVERED CSO MASTER MONITOR | {len(active_items)} ACTIVE TRADES | {now_str}")
        print(f"=======================================================================================================================")
        print(f"{'SYMBOL':<20} | {'DIR':<5} | {'ENTRY':<8} | {'MARK':<8} | {'SHARES':<6} | {'STOP':<8} | {'MTTP / HORIZON':<15} | {'PNL':<10}")
        print(f"-" * 105)

        for item in active_items:
            t_id = item.get('trade_id')
            tenant_id = item.get('tenant_id', 'COMPANY_A')
            ticker = str(item.get('ticker', '')).upper()
            occ_symbol = str(item.get('occ_symbol', ticker))
            entry_price = float(item.get('entry_price', 0.0) or 0.0)
            
            # Safe shares parsing avoiding 'None' string conversion crash
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
            stored_stop_loss = float(item.get('stop_loss', round(entry_price * 0.80, 2)) or 0.0)
            is_runner = bool(item.get('is_runner', False))
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

            pnl_pct = round(((current_price - entry_price) / entry_price) * 100.0, 2)
            peak_price = max(stored_peak, current_price)
            peak_pnl_pct = round(((peak_price - entry_price) / entry_price) * 100.0, 2)

            if is_runner:
                cushion = 10.0 if peak_pnl_pct >= 50.0 else 8.0
                dynamic_stop_pct = max(3.0, peak_pnl_pct - cushion)
                calculated_stop = round(entry_price * (1.0 + dynamic_stop_pct / 100.0), 2)
            elif peak_pnl_pct >= 35.0:
                calculated_stop = round(entry_price * (1.0 + (peak_pnl_pct - 8.0) / 100.0), 2)
            elif peak_pnl_pct >= 20.0:
                calculated_stop = round(entry_price * (1.0 + (peak_pnl_pct - 6.0) / 100.0), 2)
            elif peak_pnl_pct >= 5.0:
                calculated_stop = round(entry_price * 1.01, 2)
            else:
                calculated_stop = round(entry_price * 0.80, 2) if entry_price > 0.50 else round(max(0.02, entry_price - 0.10), 2)

            dynamic_stop = max(stored_stop_loss, calculated_stop)
            mttp_status = f"{elapsed_minutes:.1f}m / {MTTP_MAX_MINUTES}m"

            print(f"{occ_symbol:<20} | {trade_dir:<5} | ${entry_price:<7.2f} | ${current_price:<7.2f} | {total_shares:<6} |${dynamic_stop:<7.2f} | {mttp_status:<15} | {pnl_pct:+6.1f}%")

            exit_reason = None
            if current_price <= dynamic_stop and current_price > 0:
                exit_reason = f"[SCJ] DYNAMIC_TRAIL_STOP_(${dynamic_stop:.2f})"
            elif pnl_pct >= 50.0 and total_shares == 1:
                exit_reason = "[SCJ] TAKE_PROFIT_50PCT"
            elif pnl_pct <= -20.0:
                exit_reason = "[SCJ] STOP_LOSS_20PCT"
            elif elapsed_minutes >= MTTP_MAX_MINUTES and is_regular_trading_hours():
                exit_reason = f"[SCJ] MTTP_TIME_EXPIRED_{MTTP_MAX_MINUTES}M"

            table.update_item(
                Key={'tenant_id': tenant_id, 'trade_id': t_id},
                UpdateExpression='SET peak_price = :pk, stop_loss = :sl, cso_notes = :cn',
                ExpressionAttributeValues={
                    ':pk': str(peak_price), ':sl': str(dynamic_stop), ':cn': f"TRAIL_LOCK_STOP_${dynamic_stop:.2f}"
                }
            )

            if exit_reason:
                print(f"🚨 [EXIT TRIGGERED] {ticker} ({occ_symbol}) -> {exit_reason}")
                if execute_tradier_close_stepped(occ_symbol, ticker, total_shares, active_base_url):
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
                    print(f"[✓] Position Closed Successfully | Net PnL: ${total_net:+.2f}")

    except Exception as e:
        print(f"[-] Master Exit Monitor Error: {e}")

if __name__ == "__main__":
    ensure_schema()
    print("[⚙️] Auto-Discovering Master Exit Monitor Initialized.")
    sync_sqlite_to_dynamo()
    print("[🚀 ENTERING ACTIVE MASTER EXIT MONITOR LOOP...]")
    while True:
        evaluate_gex_exits()
        time.sleep(10)
