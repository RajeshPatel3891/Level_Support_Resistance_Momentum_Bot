import os
import sys
import json
import requests
import websocket
import time
import sqlite3
import signal
from datetime import datetime
from dotenv import load_dotenv

# Ensure Python can resolve the parent project directory for absolute package imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

import src.aapl_playbook as aapl
import src.tsla_playbook as tsla
import src.nvda_playbook as nvda
import src.rivn_playbook as rivn
import src.pltr_playbook as pltr

load_dotenv()

MANIFEST_PATH = os.path.join(CURRENT_DIR, 'trading_levels.json')
if not os.path.exists(MANIFEST_PATH):
    MANIFEST_PATH = os.path.join(PARENT_DIR, 'trading_levels.json')

MASTER_DATA = json.load(open(MANIFEST_PATH, 'r'))
ACTIVE_TRADES = {}
TELEMETRY = {}
PLAYBOOKS = {"AAPL": aapl, "TSLA": tsla, "NVDA": nvda, "RIVN": rivn, "PLTR": pltr}

def handle_shutdown_signal(signum, frame):
    """Force an immediate exit the millisecond Ctrl+C is pressed."""
    print("\n🛑 [SHUTDOWN] Intercepted termination signal. Exiting LiveBot safely.")
    sys.exit(0)

# Register signal interception handlers immediately on file load
signal.signal(signal.SIGINT, handle_shutdown_signal)
signal.signal(signal.SIGTERM, handle_shutdown_signal)

def sync_active_trades_from_db():
    global ACTIVE_TRADES
    try:
        conn = sqlite3.connect("harm_telemetry.db")
        cursor = conn.cursor()
        cursor.execute("SELECT ticker FROM trades WHERE exit_status = 'ACTIVE'")
        rows = cursor.fetchall()
        ACTIVE_TRADES = {row[0]: True for row in rows}
        conn.close()
        print(f"[✓] Synced ACTIVE_TRADES state from database: {list(ACTIVE_TRADES.keys())}")
    except Exception as e:
        print(f"[-] Database Sync Error: {e}", file=sys.stderr)

sync_active_trades_from_db()

def get_order_status(order_id):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"https://sandbox.tradier.com/v1/accounts/{account_id}/orders/{order_id}"
    response = requests.get(url, headers=headers)
    return response.json().get("order", {}).get("status") if response.status_code == 200 else "UNKNOWN"

def log_trade_to_database(ticker, spot_price):
    try:
        conn = sqlite3.connect("harm_telemetry.db")
        cursor = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        stop_loss = round(spot_price - 1.52, 2)
        take_profit = round(spot_price + 3.98, 2)
        cursor.execute("""
            INSERT INTO trades (ticker, timestamp, strategy, direction, spot_level, spot_price, stop_loss, take_profit, exit_status, is_live) 
            VALUES (?, ?, 'BREAKOUT', 'CALL', ?, ?, ?, ?, 'ACTIVE', 1)
        """, (ticker, timestamp, spot_price, spot_price, stop_loss, take_profit))
        conn.commit()
        conn.close()
        print(f"[✓] Logged verified trade for {ticker} to SQLite.")
    except Exception as e:
        print(f"[-] DB Log Error: {e}", file=sys.stderr)

def execute_order(symbol, ticker, quantity, side, limit_price=None):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    payload = {"class": "option", "symbol": symbol, "option_symbol": ticker, "side": side.lower(), "quantity": str(int(quantity)), "type": "limit", "price": str(limit_price) if limit_price else "0.01", "duration": "day"}
    response = requests.post(f"https://sandbox.tradier.com/v1/accounts/{account_id}/orders", data=payload, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    
    if response.status_code == 200:
        order_id = response.json().get("order", {}).get("id")
        time.sleep(2)
        if get_order_status(order_id) == "filled":
            if "buy" in side.lower():
                log_trade_to_database(symbol, 131.02)
                ACTIVE_TRADES[symbol] = True
            return True
    return False

def on_message(ws, message):
    try:
        events = json.loads(message)
        if isinstance(events, dict): events = [events]
        for e in events:
            if e.get("ev") == "T":
                sym, price = e.get("sym"), e.get("price")
                if sym in PLAYBOOKS and ACTIVE_TRADES.get(sym):
                    pass
    except Exception: pass

def run_ws_loop():
    print("[*] Starting LiveBot WebSocket listener...")
    while True:
        try:
            ws = websocket.WebSocketApp(
                "wss://ws.tradier.com/v1/markets/events", 
                on_message=on_message, 
                on_open=lambda ws: print("### Auth ###")
            )
            ws.run_forever()
            
            # Prevent high-velocity reconnection loops if network rejects session
            print("[-] Connection closed. Retrying connection in 3 seconds...")
            time.sleep(3)
            
        except Exception as e:
            print(f"[-] WS Error: {e}. Reconnecting in 5s...", file=sys.stderr)
            time.sleep(5)

if __name__ == "__main__":
    run_ws_loop()
