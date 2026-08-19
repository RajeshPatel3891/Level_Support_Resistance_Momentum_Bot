# ==============================================================================
# HARM.AI UNIFIED CHIEF STRATEGY OFFICER (CSO) MASTER EXIT MONITOR
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
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr

load_dotenv()

MANIFEST_PATH = "trading_levels.json"
MTTP_MAX_MINUTES = int(os.getenv("MTTP_MAX_MINUTES", 45))

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
    """Verify NYSE regular trading session (09:30 - 16:00 EST, Mon-Fri)."""
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(ny_tz)
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def get_gex_target_info(ticker):
    """Fetch live GEX target and spot gap from root manifest."""
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r") as f:
                data = json.load(f)
            val = data.get(ticker, {})
            spot = float(val.get("spot", val.get("last_price", 0.0)) or 0.0)
            target = float(val.get("target", val.get("gex_target", 0.0)) or 0.0)
            gap_pct = float(val.get("gap_pct", 0.0) or 0.0)
            return spot, target, gap_pct
        except Exception:
            pass
    return 0.0, 0.0, 0.0


def ensure_schema():
    """Ensure local SQLite schema supports peak prices, contract counts, and WAL mode."""
    db_file = "harm_telemetry.db"
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file, timeout=10.0)
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            for col in ["exit_timestamp TEXT", "peak_price REAL", "is_runner INTEGER", "partial_pnl REAL", "min_pnl_seen REAL"]:
                try:
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[-] Local SQLite schema warning: {e}")


def get_live_quote(occ_symbol):
    """Fetch live option mark with dynamic Live/Sandbox endpoint auto-switching."""
    if not TRADIER_TOKEN or not occ_symbol:
        return 0.0, TRADIER_BASE_URL
    
    endpoints = [
        "https://api.tradier.com/v1/markets/quotes",
        "https://sandbox.tradier.com/v1/markets/quotes"
    ]
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    
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
            
    return 0.0, TRADIER_BASE_URL


def execute_tradier_close(occ_symbol, ticker, shares, base_url, max_wait_seconds=15):
    """Execute sell_to_close order on Tradier API using Adaptive Limit Midpoint Guard & Early Momentum Urgency Intercept."""
    if not TRADIER_TOKEN or not TRADIER_ACCOUNT_ID:
        print(f"[-] Tradier credentials missing. Could not close {shares}x {occ_symbol}")
        return False
    
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    
    start_time = time.time()
    initial_midpoint = None
    best_midpoint = None
    tick_count = 0
    
    print(f"[ADAPTIVE GUARD] Monitoring order book for {occ_symbol} (Max {max_wait_seconds}s window)...")
    
    while (time.time() - start_time) < max_wait_seconds:
        tick_count += 1
        try:
            quote_res = requests.get(f"{base_url}/markets/quotes", params={"symbols": occ_symbol}, headers=headers, timeout=3)
            if quote_res.status_code == 200:
                q_data = quote_res.json().get('quotes', {}).get('quote', {})
                if isinstance(q_data, list) and q_data:
                    q_data = q_data[0]
                bid = float(q_data.get('bid', 0.0) or 0.0)
                ask = float(q_data.get('ask', 0.0) or 0.0)
                
                if bid > 0 and ask > 0:
                    current_midpoint = round((bid + ask) / 2.0, 2)
                    
                    if initial_midpoint is None:
                        initial_midpoint = current_midpoint
                        best_midpoint = current_midpoint
                    
                    # Early Urgency Intercept (Within first 3 seconds)
                    elapsed = time.time() - start_time
                    if elapsed <= 3.0:
                        if current_midpoint >= initial_midpoint * 1.015:  # 1.5% favorable bump
                            print(f"[URGENCY INTERCEPT] Favorable momentum detected at T={elapsed:.1f}s! Midpoint jumped to ${current_midpoint}. Executing immediately.")
                            best_midpoint = current_midpoint
                            break
                    
                    # Track best midpoint for selling (higher is better)
                    if current_midpoint > best_midpoint:
                        best_midpoint = current_midpoint
        except Exception as q_err:
            pass
            
        time.sleep(1.0)
        
    order_type = 'market'
    limit_price = None
    
    if best_midpoint and best_midpoint > 0:
        order_type = 'limit'
        limit_price = str(best_midpoint)
        print(f"[ADAPTIVE GUARD] Final Limit Order Pegged at: ${limit_price} after {tick_count} ticks.")
    else:
        print(f"[ADAPTIVE GUARD WARNING] Could not establish dynamic midpoint. Falling back to market order.")

    payload = {
        'class': 'option',
        'symbol': ticker,
        'option_symbol': occ_symbol,
        'side': 'sell_to_close',
        'quantity': str(abs(int(shares))),
        'type': order_type,
        'duration': 'day'
    }
    if order_type == 'limit' and limit_price:
        payload['price'] = limit_price

    try:
        res = requests.post(f"{base_url}/accounts/{TRADIER_ACCOUNT_ID}/orders", data=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            body = res.json()
            order_info = body.get('order', {})
            if order_info.get('id') or order_info.get('status') in ['ok', 'pending']:
                print(f"[✓ TRADIER CLOSE SUCCESS ({order_type.upper()})] {shares}x {occ_symbol} | Order ID: {order_info.get('id')}" + (f" | Limit Price: ${limit_price}" if limit_price else ""))
                return True
            print(f"[-] Tradier Rejected Order: {body}")
            return False
        print(f"[-] Tradier Close Error: Status {res.status_code}")
        return False
    except Exception as e:
        print(f"[-] Tradier Close Exception for {occ_symbol}: {e}")
        return False


def sync_local_sqlite_exit(t_id, ticker, exit_reason, exit_price, exit_timestamp, net_pnl=0.0, remaining_shares=0, dynamic_stop=None):
    """Dual-log exits or partial scalings to local SQLite."""
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
            trade_dir = item.get('direction', 'CALL')
            stored_peak = float(item.get('peak_price', entry_price) or entry_price)
            stored_stop_loss = float(item.get('stop_loss', 0.0) or 0.0)
            is_runner = bool(item.get('is_runner', False))
            accumulated_pnl = float(item.get('partial_pnl', 0.0) or 0.0)

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
            pnl_pct = ((current_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

            # ------------------------------------------------------------------
            # FEATURE 1: Persist min_pnl_seen (Yesterday's Drawdown Tracker)
            # ------------------------------------------------------------------
            raw_min_seen = item.get('min_pnl_seen')
            if raw_min_seen is None:
                min_seen = dollar_pnl
                table.update_item(
                    Key={'tenant_id': tenant_id, 'trade_id': t_id},
                    UpdateExpression="SET min_pnl_seen = :m",
                    ExpressionAttributeValues={':m': str(min_seen)}
                )
            else:
                db_min_seen = float(raw_min_seen)
                if dollar_pnl < db_min_seen:
                    min_seen = dollar_pnl
                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': t_id},
                        UpdateExpression="SET min_pnl_seen = :m",
                        ExpressionAttributeValues={':m': str(min_seen)}
                    )
                else:
                    min_seen = db_min_seen

            # ------------------------------------------------------------------
            # FEATURE 2: High-Water Mark Peak PnL Tracking (Today's Engine)
            # ------------------------------------------------------------------
            peak_price = max(stored_peak, current_price)
            peak_pnl_pct = ((peak_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

            # --- DYNAMIC TRAILING STOP DOLLAR CALCULATION ---
            if is_runner:
                cushion = 12.0 if peak_pnl_pct >= 100.0 else 10.0
                dynamic_stop_pct = max(3.0, peak_pnl_pct - cushion)
                dynamic_stop = round(entry_price * (1.0 + dynamic_stop_pct / 100.0), 2)
            elif peak_pnl_pct >= 35.0:
                dynamic_stop = round(entry_price * (1.0 + (peak_pnl_pct - 10.0) / 100.0), 2)
            elif peak_pnl_pct >= 20.0:
                dynamic_stop = round(entry_price * (1.0 + (peak_pnl_pct - 10.0) / 100.0), 2)
            elif peak_pnl_pct >= 12.0:
                dynamic_stop = round(entry_price * 1.03, 2)
            else:
                if entry_price <= 0.50:
                    calculated_stop = round(max(0.02, entry_price - 0.10), 2)
                else:
                    calculated_stop = round(entry_price * 0.80, 2)

                # Prevent downward ratcheting of existing stop loss
                dynamic_stop = max(stored_stop_loss, calculated_stop)

            # Persist Peak Price, Dynamic Stop Loss & Min PnL to DynamoDB
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

            print(f"[⚙️ MASTER EXIT] {ticker} | {total_shares}x | Entry: ${entry_price:.2f} | Live: ${current_price:.2f} ({pnl_pct:+.1f}%) | Peak: ${peak_price:.2f} (+{peak_pnl_pct:.1f}%) | Active Stop: ${dynamic_stop:.2f} | Min Seen: ${min_seen:+.2f}")

            # ------------------------------------------------------------------
            # FEATURE 3: Red-to-Green Recovery Exit (Bail out if trade dipped)
            # ------------------------------------------------------------------
            if min_seen < 0.0 and dollar_pnl >= 1.00:
                print(f"🛡️ [GSG RECOVERY EXIT] {ticker} dipped red (${min_seen:.2f}) & recovered to green (+${dollar_pnl:.2f}). CLOSING!")
                if execute_tradier_close(occ_symbol, ticker, total_shares, active_base_url):
                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': t_id},
                        UpdateExpression="SET exit_status = :st, exit_price = :px, net_pnl = :pnl, cso_reason = :st, shares = :sh",
                        ExpressionAttributeValues={':st': 'GSG_RECOVERY_CLOSE', ':px': str(current_price), ':pnl': str(dollar_pnl), ':sh': '0'}
                    )
                    sync_local_sqlite_exit(t_id, ticker, "GSG_RECOVERY_CLOSE", current_price, now_str, dollar_pnl, remaining_shares=0)
                continue

            # ------------------------------------------------------------------
            # FEATURE 4: Multi-Contract Tranche Scaling (+50% / GEX Target)
            # ------------------------------------------------------------------
            if total_shares > 1 and not is_runner and (pnl_pct >= 50.0 or (gex_gap_pct != 0.0 and abs(gex_gap_pct) <= 0.5)):
                scale_shares = total_shares - 1
                realized_scale_pnl = round((current_price - entry_price) * scale_shares * 100.0, 2)
                
                print(f"🚀 [CSO TRANCHE EXIT] Scaling {scale_shares}x contracts on {ticker} at {pnl_pct:+.1f}% | Banking ${realized_scale_pnl:+.2f} | Leaving 1 RUNNER")
                
                if execute_tradier_close(occ_symbol, ticker, scale_shares, active_base_url):
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

            # ------------------------------------------------------------------
            # FEATURE 5: Dynamic Trailing & Hard Risk Exits (CSO Informed)
            # ------------------------------------------------------------------
            exit_reason = None

            # 1. Trailing Stop Floor Triggered
            if current_price <= dynamic_stop and current_price > 0:
                exit_reason = f"DYNAMIC_TRAIL_STOP_TRIGGERED_(${dynamic_stop:.2f})"

            # 2. Hard Target Cap (+50% Single Contract)
            elif pnl_pct >= 50.0 and total_shares == 1:
                exit_reason = "TAKE_PROFIT_50PCT"

            # 3. CSO Early Momentum Cut (-8% to -19.9% soft band)
            elif -20.0 < pnl_pct <= -8.0 and spot > 0:
                support_lvl = float(get_gex_target_info(ticker)[0] or 0.0)
                if support_lvl > 0 and spot < support_lvl:
                    exit_reason = f"CSO_EARLY_MOMENTUM_CUT_({pnl_pct:.1f}%)"

            # 4. Hard Safety Floor (-20%)
            elif pnl_pct <= -20.0:
                exit_reason = "STOP_LOSS_20PCT"

            # 5. Time Expiration
            elif elapsed_minutes >= MTTP_MAX_MINUTES and is_regular_trading_hours():
                exit_reason = f"MTTP_TIME_EXPIRED_{MTTP_MAX_MINUTES}M"

            if exit_reason:
                print(f"🚨 [FINAL EXIT TRIGGERED] ID {t_id} ({ticker} {occ_symbol}) -> Reason: {exit_reason} at {now_str}")
                if execute_tradier_close(occ_symbol, ticker, total_shares, active_base_url):
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
    while True:
        evaluate_gex_exits()
        time.sleep(10)
