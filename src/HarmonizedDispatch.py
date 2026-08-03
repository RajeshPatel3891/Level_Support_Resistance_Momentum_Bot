import os
import sys
import json
import sqlite3
import requests
import time
from datetime import datetime

# Fetch environment tag; defaults to UNKNOWN-ORIGIN if omitted
EXECUTION_ORIGIN = os.getenv("EXECUTION_ORIGIN", "UNKNOWN-ORIGIN")

def init_db(db_path='harm_telemetry.db'):
    """Ensures database table, execution_origin column, and unique composite index exist for UPSERT deduplication."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. Create table with full schema if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            timestamp TEXT,
            strategy TEXT,
            direction TEXT,
            spot_price REAL,
            exit_price REAL,
            exit_status TEXT,
            net_pnl REAL,
            execution_origin TEXT DEFAULT 'UNKNOWN-ORIGIN'
        )
    ''')
    
    # 2. Migration check: Add execution_origin column if missing from legacy tables
    cursor.execute("PRAGMA table_info(trades);")
    columns = [column[1] for column in cursor.fetchall()]
    if "execution_origin" not in columns:
        cursor.execute("ALTER TABLE trades ADD COLUMN execution_origin TEXT DEFAULT 'LEGACY';")
        print("[✓] Migrated 'trades' table: Added 'execution_origin' column.")

    # 3. Ensure deduplication index exists
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dedup_trades 
        ON trades(ticker, spot_price, exit_price, exit_status)
    ''')
    
    conn.commit()
    conn.close()

def sanitize_historical_telemetry(db_paths=['harm_telemetry.db']):
    """Auto-sanitizes historical telemetry on engine startup by purging duplicate records."""
    for db in db_paths:
        if not os.path.exists(db):
            continue
        try:
            conn = sqlite3.connect(db)
            cursor = conn.cursor()
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            target_table = 'trades' if 'trades' in tables else None
                
            if target_table:
                cursor.execute(f'''
                    DELETE FROM {target_table}
                    WHERE id NOT IN (
                        SELECT MIN(id)
                        FROM {target_table}
                        GROUP BY ticker, spot_price, exit_price, exit_status
                    );
                ''')
                conn.commit()
                print(f"[+] Auto-sanitized telemetry in {db} (table: {target_table})")
            conn.close()
        except Exception as e:
            print(f"[!] Warning: Auto-sanitization skipped for {db}: {e}")

def check_cash_availability(required_capital, db_path='harm_telemetry.db'):
    """Validates if today's available settled cash covers the required trade capital."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT available_settled_cash FROM account_ledger WHERE date = ?", (today_str,))
        row = cursor.fetchone()
        conn.close()
        
        available = float(row[0]) if row else 0.0
        if available >= required_capital:
            return True, available
            
        print(f"[!] REJECTED: Insufficient Settled Cash (${available:,.2f} available, ${required_capital:,.2f} required)")
        return False, available
    except Exception as e:
        print(f"[!] Ledger Check Error: {e}")
        return False, 0.0

def log_trade_event(trade_data, db_path='harm_telemetry.db'):
    """Logs or updates a trade record using SQLite UPSERT pattern with execution origin tracking."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    origin = os.getenv("EXECUTION_ORIGIN", "UNKNOWN-ORIGIN")
    
    # Ensure execution_origin is present in payload dict
    payload = dict(trade_data)
    payload['execution_origin'] = payload.get('execution_origin', origin)
    
    query = '''
        INSERT INTO trades (
            ticker, timestamp, strategy, direction, 
            spot_price, exit_price, exit_status, net_pnl, execution_origin
        ) VALUES (
            :ticker, :timestamp, :strategy, :direction, 
            :spot_price, :exit_price, :exit_status, :net_pnl, :execution_origin
        )
        ON CONFLICT(ticker, spot_price, exit_price, exit_status) DO UPDATE SET
            timestamp = EXCLUDED.timestamp,
            net_pnl = EXCLUDED.net_pnl,
            execution_origin = EXCLUDED.execution_origin;
    '''
    try:
        cursor.execute(query, payload)
        conn.commit()
        print(f"[✓] Trade logged for {payload.get('ticker')} | Marker: {payload['execution_origin']}")
    except Exception as e:
        print(f"[!] Database log error: {e}")
    finally:
        conn.close()

def force_exit_all(symbol, limit_price=None, force_market=False):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        orders_resp = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers).json()
    except Exception:
        orders_resp = {}

    if not isinstance(orders_resp, dict):
        orders_resp = {}
        
    orders_data = orders_resp.get('orders', {})
    orders = orders_data.get('order', []) if isinstance(orders_data, dict) else []

    if isinstance(orders, dict):
        orders = [orders]
        
    if any(o.get('option_symbol') == symbol and o.get('status') == 'open' for o in orders if isinstance(o, dict)):
        return "Order already pending."

    try:
        pos_data = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers).json()
    except Exception:
        pos_data = {}

    positions_data = pos_data.get('positions', {}) if isinstance(pos_data, dict) else {}
    positions = positions_data.get('position', []) if isinstance(positions_data, dict) else []

    if isinstance(positions, dict):
        positions = [positions]
    
    target = next((p for p in positions if isinstance(p, dict) and p.get('symbol') == symbol), None)
    if not target:
        return "No position found."
    
    return "Routing processing complete."

if __name__ == "__main__":
    print("=" * 65)
    print("[+] HARMONIZED AI DISPATCH ENGINE INITIALIZED")
    print("Target Session: August 3, 2026 | Session Bell: Active")
    print(f"Execution Marker: {EXECUTION_ORIGIN}")
    print("=" * 65)

    # Initialize database tables and deduplication constraints
    init_db()

    # Auto-sanitize historical telemetry on startup
    sanitize_historical_telemetry()

    try:
        with open('trading_levels.json', 'r') as f:
            levels = json.load(f)
        print(f"[+] Loaded trading_levels.json successfully ({len([k for k, v in levels.items() if isinstance(v, dict) and ('support_a' in v or 'support_zone' in v or 'spot_target_call' in v)])} tickers tracked)")
    except Exception as e:
        print(f"[!] Warning: Could not load trading_levels.json: {e}")

    print("[+] Starting Live Exception Dispatch Loop...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] Dispatch Engine stopped.")
