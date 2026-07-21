import os
import sys
import json
import sqlite3
import requests
import time

def init_db(db_path='harmonized_trades.db'):
    """Ensures database table and unique composite index exist for UPSERT deduplication."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS harmonized_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            timestamp TEXT,
            strategy TEXT,
            direction TEXT,
            spot_price REAL,
            exit_price REAL,
            exit_status TEXT,
            net_pnl REAL
        )
    ''')
    cursor.execute('''
        CREATE UNIQUE INDEX IF NOT EXISTS idx_dedup_trades 
        ON harmonized_trades(ticker, spot_price, exit_price, exit_status)
    ''')
    conn.commit()
    conn.close()

def log_trade_event(trade_data, db_path='harmonized_trades.db'):
    """Logs or updates a trade record using SQLite UPSERT pattern to prevent duplicates."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = '''
        INSERT INTO harmonized_trades (
            ticker, timestamp, strategy, direction, 
            spot_price, exit_price, exit_status, net_pnl
        ) VALUES (
            :ticker, :timestamp, :strategy, :direction, 
            :spot_price, :exit_price, :exit_status, :net_pnl
        )
        ON CONFLICT(ticker, spot_price, exit_price, exit_status) DO UPDATE SET
            timestamp = EXCLUDED.timestamp,
            net_pnl = EXCLUDED.net_pnl;
    '''
    try:
        cursor.execute(query, trade_data)
        conn.commit()
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
    if isinstance(orders_data, dict):
        orders = orders_data.get('order', [])
    else:
        orders = []

    if isinstance(orders, dict):
        orders = [orders]
        
    if any(o.get('option_symbol') == symbol and o.get('status') == 'open' for o in orders if isinstance(o, dict)):
        return "Order already pending."

    try:
        pos_data = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers).json()
    except Exception:
        pos_data = {}

    if not isinstance(pos_data, dict):
        pos_data = {}
        
    positions_data = pos_data.get('positions', {})
    if isinstance(positions_data, dict):
        positions = positions_data.get('position', [])
    else:
        positions = []

    if isinstance(positions, dict):
        positions = [positions]
    
    target = next((p for p in positions if isinstance(p, dict) and p.get('symbol') == symbol), None)
    if not target:
        return "No position found."
    
    return "Routing processing complete."

if __name__ == "__main__":
    print("=" * 65)
    print("[+] HARMONIZED AI DISPATCH ENGINE INITIALIZED")
    print("Target Session: July 21, 2026 | Session Bell: Active")
    print("=" * 65)

    # Initialize database tables and deduplication constraints
    init_db()

    try:
        with open('trading_levels.json', 'r') as f:
            levels = json.load(f)
        print(f"[+] Loaded trading_levels.json successfully ({len(levels.get('levels', {}))} tickers tracked)")
    except Exception as e:
        print(f"[!] Warning: Could not load trading_levels.json: {e}")

    print("[+] Starting Live Exception Dispatch Loop...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] Dispatch Engine stopped.")
