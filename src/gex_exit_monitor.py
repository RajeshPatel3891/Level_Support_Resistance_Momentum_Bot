import os
import sys
import time
import json
import sqlite3
import requests
import boto3
from datetime import datetime
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr

load_dotenv()

MANIFEST_PATH = "trading_levels.json"
MTTP_MAX_MINUTES = int(os.getenv("MTTP_MAX_MINUTES", 45))

# Tradier Broker Config
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
TRADIER_TOKEN = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")


def get_live_spot(ticker):
    """Safely fetch live spot price from trading_levels.json root manifest."""
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r") as f:
                data = json.load(f)
            val = data.get(ticker, {})
            spot = val.get("spot", val.get("last_price", 0.0))
            if spot and float(spot) > 0:
                return float(spot)
        except Exception:
            pass
    return 0.0


def ensure_schema():
    """Ensure required local SQLite schema columns exist to prevent operational halts if local DB exists."""
    db_file = "harm_telemetry.db"
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file, timeout=10.0)
            cursor = conn.cursor()
            try:
                cursor.execute("ALTER TABLE trades ADD COLUMN exit_timestamp TEXT")
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Column already exists
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
    """Execute sell_to_close market order on Tradier API."""
    if not TRADIER_TOKEN or not TRADIER_ACCOUNT_ID:
        print(f"[-] Tradier credentials missing. Could not close {occ_symbol}")
        return False
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    payload = {
        'class': 'option',
        'symbol': ticker,
        'option_symbol': occ_symbol,
        'side': 'sell_to_close',
        'quantity': str(abs(float(shares))),
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
        print(f"[✓] Tradier Close Order Sent for {occ_symbol} | Status: {res.status_code}")
        return res.status_code == 200
    except Exception as e:
        print(f"[-] Tradier Close Error for {occ_symbol}: {e}")
        return False


def sync_local_sqlite_exit(t_id, ticker, exit_reason, exit_price, exit_timestamp):
    """Dual-log exit to local SQLite so LiveBot duplicate-entry guards stay in sync."""
    db_file = "harm_telemetry.db"
    if os.path.exists(db_file):
        try:
            conn = sqlite3.connect(db_file, timeout=5.0)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE trades SET exit_status = ?, exit_price = ?, exit_timestamp = ? WHERE id = ? OR ticker = ?",
                (exit_reason, exit_price, exit_timestamp, t_id, ticker)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[-] Local SQLite exit sync warning: {e}")


def evaluate_gex_exits():
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        
        # Query active positions directly from DynamoDB
        res = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        active_items = res.get('Items', [])

        if not active_items:
            print("[⚙️ GEX/MTTP MONITOR] Scanning... 0 active trades pending GEX exit.")
            return

        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        for item in active_items:
            t_id = item.get('trade_id')
            tenant_id = item.get('tenant_id', 'default')
            ticker = item.get('ticker')
            occ_symbol = item.get('occ_symbol', ticker)
            entry_price = float(item.get('entry_price', 0.0))
            shares = float(item.get('shares', 1.0))
            ts_str = item.get('timestamp')
            trade_dir = item.get('direction', 'CALL')

            if entry_price <= 0:
                continue

            # Calculate elapsed time in trade
            elapsed_minutes = 0.0
            if ts_str:
                try:
                    clean_ts = str(ts_str).split('.')[0].replace('T', ' ')
                    entry_dt = datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
                    elapsed_minutes = round((now - entry_dt).total_seconds() / 60.0, 1)
                except Exception:
                    pass

            # Fetch live option quote; fallback to root manifest spot if option quote is unavailable
            quote = get_live_quote(occ_symbol)
            manifest_spot = get_live_spot(ticker)
            current_price = float(quote.get('bid', quote.get('last', manifest_spot or entry_price))) if quote else (manifest_spot or entry_price)
            pnl_pct = ((current_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

            print(f"[⚙️ MTTP MONITOR] ID {t_id} ({ticker} {trade_dir}) | Entry: ${entry_price:.2f} | Current: ${current_price:.2f} ({pnl_pct:+.1f}%) | Time: {elapsed_minutes}m/{MTTP_MAX_MINUTES}m")

            exit_reason = None

            # Rule 1: MTTP Maximum Time-in-Trade Expiration Trigger (>45m)
            if elapsed_minutes >= MTTP_MAX_MINUTES:
                exit_reason = f"MTTP_TIME_EXPIRED_{MTTP_MAX_MINUTES}M"

            # Rule 2: Hard Stop Loss (-20%)
            elif pnl_pct <= -20.0:
                exit_reason = "STOP_LOSS_20PCT"

            # Rule 3: Take Profit Target (+50%)
            elif pnl_pct >= 50.0:
                exit_reason = "TAKE_PROFIT_50PCT"

            # Execute Exit if any rule triggered
            if exit_reason:
                print(f"🚨 [MTTP EXIT TRIGGERED] ID {t_id} ({ticker} {occ_symbol}) -> Reason: {exit_reason} logged at {now_str}")
                
                # 1. Dispatch real sell_to_close order on Tradier Broker API
                execute_tradier_close(occ_symbol, ticker, shares)

                # 2. Update Primary DynamoDB State
                table.update_item(
                    Key={'tenant_id': tenant_id, 'trade_id': t_id},
                    UpdateExpression='SET exit_status = :status, exit_price = :px, exit_timestamp = :ts',
                    ExpressionAttributeValues={
                        ':status': exit_reason,
                        ':px': str(current_price),
                        ':ts': now_str
                    }
                )
                
                # 3. Dual-log to local SQLite so LiveBot re-entry guards clear
                sync_local_sqlite_exit(t_id, ticker, exit_reason, current_price, now_str)

                print(f"[✓] Exit Logged to DynamoDB for {ticker} at {now_str}")

    except Exception as e:
        print(f"[-] GEX Exit Monitor Error: {e}")


if __name__ == "__main__":
    ensure_schema()
    print("[⚙️] GEX & MTTP Active Exit Monitor Routine Initialized.")
    while True:
        evaluate_gex_exits()
        time.sleep(10)
