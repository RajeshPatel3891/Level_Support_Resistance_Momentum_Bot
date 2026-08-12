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

# Tradier Broker Config
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
TRADIER_TOKEN = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")


def is_regular_trading_hours():
    """Verify NYSE regular trading session (09:30 - 16:00 EST, Mon-Fri)."""
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.datetime.now(ny_tz)
    if now.weekday() >= 5:  # Weekend check
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


def get_live_spot(ticker):
    """Safely fetch live spot price from trading_levels.json root manifest."""
    spot, _, _ = get_gex_target_info(ticker)
    return spot


def ensure_schema():
    """Ensure local SQLite schema supports peak prices, contract counts, and WAL concurrency mode."""
    db_file = "harm_telemetry.db"
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file, timeout=10.0)
            cursor = conn.cursor()
            
            # Enable Write-Ahead Logging (WAL) for high concurrency
            cursor.execute("PRAGMA journal_mode=WAL;")
            
            for col in ["exit_timestamp TEXT", "peak_price REAL", "is_runner INTEGER", "partial_pnl REAL"]:
                try:
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[-] Local SQLite schema verification warning: {e}")


def get_live_quote(occ_symbol):
    """Fetch live option bid/ask from Tradier API."""
    if not TRADIER_TOKEN or not TRADIER_ACCOUNT_ID:
        return {}
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    try:
        res = requests.get(
            f"{TRADIER_BASE_URL}/markets/quotes",
            params={'symbols': occ_symbol},
            headers=headers,
            timeout=3
        )
        if res.status_code == 200:
            data = res.json().get('quotes', {}).get('quote', {})
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def execute_tradier_close(occ_symbol, ticker, shares):
    """Execute sell_to_close market order on Tradier API and validate order ID in body."""
    if not TRADIER_TOKEN or not TRADIER_ACCOUNT_ID:
        print(f"[-] Tradier credentials missing. Could not close {shares}x {occ_symbol}")
        return False
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    payload = {
        'class': 'option',
        'symbol': ticker,
        'option_symbol': occ_symbol,
        'side': 'sell_to_close',
        'quantity': str(abs(int(shares))),
        'type': 'market',
        'duration': 'day'
    }
    try:
        res = requests.post(
            f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders",
            data=payload,
            headers=headers,
            timeout=5
        )
        # Check for order ID in response body to confirm execution
        if res.status_code == 200:
            body = res.json()
            order_info = body.get('order', {})
            if order_info.get('id') or order_info.get('status') in ['ok', 'pending']:
                print(f"[✓] Tradier Close Order Confirmed: {shares}x {occ_symbol} | Order ID: {order_info.get('id')}")
                return True
            print(f"[-] Tradier Rejected Order: {body}")
            return False
        print(f"[-] Tradier Close Error: Status {res.status_code}")
        return False
    except Exception as e:
        print(f"[-] Tradier Close Exception for {occ_symbol}: {e}")
        return False


def sync_local_sqlite_exit(t_id, ticker, exit_reason, exit_price, exit_timestamp, net_pnl=0.0, remaining_shares=0):
    """Dual-log exits or partial scalings to local SQLite so LiveBot guards stay synchronized."""
    db_file = "harm_telemetry.db"
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file, timeout=5.0)
            cursor = conn.cursor()
            status = exit_reason if remaining_shares == 0 else "SMART_CSO_RUNNER"
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
        
        # Scan only ACTIVE trades directly from DynamoDB
        res = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        active_items = res.get('Items', [])

        if not active_items:
            print("[⚙️ GEX/MTTP MONITOR] Scanning... 0 active trades pending GEX exit.")
            return

        now = dt.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        allowed_tickers = [t.strip().upper() for t in os.getenv("ACTIVE_TICKERS", "").split(",") if t.strip()]

        for item in active_items:
            t_id = item.get('trade_id')
            tenant_id = item.get('tenant_id', 'default')
            ticker = item.get('ticker', '').upper()

            # Dynamic Ticker Filter Guard
            if allowed_tickers and ticker not in allowed_tickers:
                continue

            occ_symbol = item.get('occ_symbol', ticker)
            entry_price = float(item.get('entry_price', 0.0))
            total_shares = int(float(item.get('shares', 1.0)))
            ts_str = item.get('timestamp')
            trade_dir = item.get('direction', 'CALL')
            stored_peak = float(item.get('peak_price', entry_price) or entry_price)
            is_runner = bool(item.get('is_runner', False))
            accumulated_pnl = float(item.get('partial_pnl', 0.0) or 0.0)

            if entry_price <= 0:
                continue

            # Calculate elapsed time in trade
            elapsed_minutes = 0.0
            if ts_str:
                try:
                    clean_ts = str(ts_str).split('.')[0].replace('T', ' ')
                    entry_dt = dt.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
                    elapsed_minutes = round((now - entry_dt).total_seconds() / 60.0, 1)
                except Exception:
                    pass

            # Fetch live quote and GEMMA target info
            quote = get_live_quote(occ_symbol)
            spot, gex_target, gex_gap_pct = get_gex_target_info(ticker)

            # Skip tick if API quote failed to prevent false trailing exits
            if not quote or ('bid' not in quote and 'last' not in quote):
                print(f"[!] Quote unavailable for {occ_symbol}. Skipping exit evaluation this tick to prevent false trailing exits.")
                continue

            current_price = float(quote.get('bid', quote.get('last')))

            # High-Water Mark (Peak Price) Update
            peak_price = max(stored_peak, current_price)
            if peak_price > stored_peak:
                table.update_item(
                    Key={'tenant_id': tenant_id, 'trade_id': t_id},
                    UpdateExpression='SET peak_price = :pk',
                    ExpressionAttributeValues={':pk': str(peak_price)}
                )

            pnl_pct = ((current_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0
            peak_pnl_pct = ((peak_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

            print(f"[⚙️ MTTP MONITOR] ID {t_id} ({ticker} {trade_dir}) | {total_shares}x {'[RUNNER]' if is_runner else '[CORE]'} | Entry: ${entry_price:.2f} | Current: ${current_price:.2f} ({pnl_pct:+.1f}%) | Peak: ${peak_price:.2f} (+{peak_pnl_pct:.1f}%) | GEMMA Gap: {gex_gap_pct:.2f}%")

            # --- CSO / GEMMA DYNAMIC TRAILING & MULTI-CONTRACT TRANCHING ENGINE ---
            
            # Scenario A: Multi-Contract Scale-Out Trigger (+50% Target Cap or GEMMA Target Hit)
            if total_shares > 1 and not is_runner and (pnl_pct >= 50.0 or (gex_gap_pct != 0.0 and abs(gex_gap_pct) <= 0.5)):
                scale_shares = total_shares - 1  # Leave exactly 1 runner
                realized_scale_pnl = round((current_price - entry_price) * scale_shares * 100.0, 2)
                
                print(f"🚀 [CSO TRANCHE EXIT] Scaling {scale_shares}x contracts on {ticker} at {pnl_pct:+.1f}% | Banking ${realized_scale_pnl:+.2f} | Leaving 1 RUNNER")
                
                if execute_tradier_close(occ_symbol, ticker, scale_shares):
                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': t_id},
                        UpdateExpression='SET shares = :sh, is_runner = :r, partial_pnl = :pp, peak_price = :pk, cso_status = :cs',
                        ExpressionAttributeValues={
                            ':sh': '1',
                            ':r': True,
                            ':pp': str(accumulated_pnl + realized_scale_pnl),
                            ':pk': str(peak_price),
                            ':cs': 'SMART_CSO_RUNNER'
                        }
                    )
                    sync_local_sqlite_exit(t_id, ticker, "PARTIAL_SCALE_OUT", current_price, now_str, realized_scale_pnl, remaining_shares=1)
                continue

            # Scenario B: Full / Final Exit Conditions
            exit_reason = None

            # 1. Runner Trailing Stop (Dynamic GEMMA Room)
            if is_runner:
                trail_cushion = 12.0 if peak_pnl_pct >= 100.0 else 10.0
                if pnl_pct <= (peak_pnl_pct - trail_cushion):
                    exit_reason = f"SMART_CSO_RUNNER_TRAIL_LOCK_(PEAK_{peak_pnl_pct:.0f}PCT)"

            # 2. Single Contract Core Target Cap (+50%)
            elif pnl_pct >= 50.0 and total_shares == 1:
                exit_reason = "MTTP_TARGET_CAP_50PCT"

            # 3. Tier 3 High Peak Trailing Cut (+35%+ Peak, Pullback > 10%)
            elif peak_pnl_pct >= 35.0 and pnl_pct <= (peak_pnl_pct - 10.0):
                exit_reason = f"MTTP_TRAIL_TIER3_LOCK_(PEAK_{peak_pnl_pct:.0f}PCT)"

            # 4. Tier 2 Mid Peak Trailing Cut (+20%+ Peak, Pullback > 10%)
            elif peak_pnl_pct >= 20.0 and pnl_pct <= (peak_pnl_pct - 10.0):
                exit_reason = f"MTTP_TRAIL_TIER2_LOCK_(PEAK_{peak_pnl_pct:.0f}PCT)"

            # 5. Tier 1 "Green Stay Green" Lock (+12%+ Peak, Pullback to +3% Floor)
            elif peak_pnl_pct >= 12.0 and pnl_pct <= 3.0:
                exit_reason = f"MTTP_GREEN_STAY_GREEN_LOCK_(PEAK_{peak_pnl_pct:.0f}PCT)"

            # 6. Hard Risk Floor (-20% Stop Loss)
            elif pnl_pct <= -20.0:
                exit_reason = "STOP_LOSS_20PCT"

            # 7. Time Expiration (>45m in trade during RTH)
            elif elapsed_minutes >= MTTP_MAX_MINUTES and is_regular_trading_hours():
                exit_reason = f"MTTP_TIME_EXPIRED_{MTTP_MAX_MINUTES}M"

            # Execute Final Exit
            if exit_reason:
                print(f"🚨 [FINAL EXIT TRIGGERED] ID {t_id} ({ticker} {occ_symbol}) -> Reason: {exit_reason} logged at {now_str}")
                
                if execute_tradier_close(occ_symbol, ticker, total_shares):
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
        print(f"[-] GEX Exit Monitor Error: {e}")


if __name__ == "__main__":
    ensure_schema()
    print("[⚙️] GEX & MTTP Active Exit Monitor Routine Initialized.")
    while True:
        evaluate_gex_exits()
        time.sleep(10)
