import os
import requests
import queue
import threading
import sys
import json
import websocket
import time
import sqlite3
import signal
import pytz
from datetime import datetime
from dotenv import load_dotenv

def dispatch_discord_alert(symbol, basis, action="ENTRY"):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url or "your_real_id" in webhook_url:
        return
    payload = {
        "embeds": [{
            "title": "🦅 HARM.AI // EXECUTION ENGINE SIGNAL",
            "color": 3066993 if action == "ENTRY" else 15158332,
            "fields": [
                {"name": "Asset Ticker", "value": f"`{symbol}`", "inline": True},
                {"name": "Action Taken", "value": f"**{action}**", "inline": True},
                {"name": "Execution Price", "value": f"`${basis:.2f}`", "inline": True}
            ],
            "footer": {"text": "Harmonized Real-Time Stream Engine Active"}
        }]
    }
    try:
        requests.post(webhook_url, json=payload, timeout=5)
    except:
        pass

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
from src.GexReader import get_latest_gex_context

load_dotenv()

MANIFEST_PATH = os.path.join(CURRENT_DIR, 'trading_levels.json')
if not os.path.exists(MANIFEST_PATH):
    MANIFEST_PATH = os.path.join(PARENT_DIR, 'trading_levels.json')

MASTER_DATA = json.load(open(MANIFEST_PATH, 'r'))
ACTIVE_TRADES = {}
TELEMETRY = {}
PLAYBOOKS = {"AAPL": aapl, "TSLA": tsla, "NVDA": nvda, "RIVN": rivn, "PLTR": pltr}

def is_market_hours():
    """Checks if current time is within standard US equity market hours (09:30 - 16:00 EST, Mon-Fri)."""
    est = pytz.timezone('US/Eastern')
    now_est = datetime.now(est)
    if now_est.weekday() >= 5:
        return False
    market_open = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_est.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_est <= market_close

def evaluate_ticker_risk(symbol):
    """Fetch the serverless-calculated metrics from your local SQLite layer."""
    gex_data = get_latest_gex_context(symbol)
    
    if gex_data:
        label = gex_data['gex_label']
        net_gex = gex_data['net_gex']
        print(f"[*] Core Engine reading local matrix for {symbol}: {label} GEX (${net_gex:,.2f})")
        
        if label == "NEGATIVE":
            # Action: Tighten up risk parameters due to implied dealer hedging loops
            print(f"[!] Warning: High-volatility dealer regime detected for {symbol}. Applying strict risk filters.")
            return "HIGH_VOLATILITY_MODE"
        else:
            return "STANDARD_REGIME"
            
    return "NO_CONTEXT"

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
    token = os.getenv("TRADIER_TOKEN") or os.getenv("TRADIER_SANDBOX_TOKEN")
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
            INSERT INTO trades (ticker, timestamp, strategy, direction, spot_level, spot_price, stop_loss, take_profit, net_pnl, exit_status, is_live) 
            VALUES (?, ?, 'BREAKOUT', 'CALL', ?, ?, ?, ?, 0.0, 'ACTIVE', 1)
        """, (ticker, timestamp, spot_price, spot_price, stop_loss, take_profit))
        conn.commit()
        conn.close()
        print(f"[✓] Logged verified trade for {ticker} to SQLite.")
    except Exception as e:
        print(f"[-] DB Log Error: {e}", file=sys.stderr)


# --- NON-BLOCKING TELEMETRY QUEUE ENGINE ---
tick_queue = queue.Queue()

def db_batch_worker():
    print("[*] Launching async database writer thread...")
    conn = sqlite3.connect("harm_telemetry.db", check_same_thread=False)
    cursor = conn.cursor()
    
    while True:
        batch = []
        # Gather all items currently waiting in the thread queue
        while True:
            try:
                batch.append(tick_queue.get_nowait())
            except queue.Empty:
                break
        
        if batch:
            try:
                cursor.executemany(
                    "INSERT INTO tick_history (ticker, timestamp, price) VALUES (?, ?, ?)", 
                    batch
                )
                conn.commit()
            except Exception as e:
                print(f"[-] Asynchronous Batch Write Error: {e}", file=sys.stderr)
        
        time.sleep(5) # Wake up every 5 seconds to clear the queue buffer

# Boot the worker immediately as a background daemon thread
threading.Thread(target=db_batch_worker, daemon=True).start()

def execute_order(symbol, ticker, quantity, side, limit_price=None):
    token = os.getenv("TRADIER_TOKEN") or os.getenv("TRADIER_SANDBOX_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    payload = {"class": "option", "symbol": symbol, "option_symbol": ticker, "side": side.lower(), "quantity": str(int(quantity)), "type": "limit", "price": str(limit_price) if limit_price else "0.01", "duration": "day"}
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    response = requests.post(f"{base_url}/accounts/{account_id}/orders", data=payload, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    
    if response.status_code == 200:
        order_id = response.json().get("order", {}).get("id")
        time.sleep(2)
        if get_order_status(order_id) == "filled":
            if "buy" in side.lower():
                log_trade_to_database(symbol, float(limit_price) if limit_price else 1.00)
                try:
                    dispatch_discord_alert(symbol, float(limit_price) if limit_price else 1.00, 'ENTRY')
                except:
                    pass
                ACTIVE_TRADES[symbol] = True
            return True
    return False

def on_message(ws, message):
    if not is_market_hours():
        return  # Ignore after-hours synthetic ticks for live order execution

    try:
        events = json.loads(message)
        if isinstance(events, dict): events = [events]
        for e in events:
            if e.get("type") == "trade":
                sym, price = e.get("symbol"), e.get("price")
                # Drop raw telemetry into background thread instantly without locking the websocket loop
                tick_queue.put((sym, datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), float(price)))
                print(f"[+] TICKER HIT -> {sym}: ${price}")
                if sym in PLAYBOOKS:
                    # Intercept the incoming price tick with our local ultra-low latency GEX matrix
                    regime = evaluate_ticker_risk(sym)
                    
                    if ACTIVE_TRADES.get(sym):
                        # Existing position management playbook logic can be evaluated here
                        pass
                    else:
                        # Run your playbook signal strategies (Breakout, S/R, Momentum)
                        # If regime == "HIGH_VOLATILITY_MODE", your playbooks can tighten stop-losses dynamically
                        pass
    except Exception:
        pass

def get_streaming_session():
    token = os.getenv("TRADIER_TOKEN") or os.getenv("TRADIER_SANDBOX_TOKEN")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        # Request a dynamic WebSocket session ticket from the REST engine
        base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
        r = requests.post(f"{base_url}/markets/events/session", headers=headers)
        if r.status_code == 200:
            return r.json().get("stream", {})
    except Exception as e:
        print(f"[-] Session API Request Error: {e}")
    return {}

def on_ws_open(ws):
    session_info = get_streaming_session()
    session_id = session_info.get("sessionid")
    
    if session_id:
        # Formulate the explicit Tradier payload layout to subscribe to your core watchlist pool
        auth_payload = {
            "symbols": ["AAPL", "NVDA", "TSLA", "PLTR", "RIVN", "SOFI", "INTC", "AAL", "F"],
            "lineage": "true",
            "sessionid": session_id,
            "breakdown": "true"
        }
        print(f"[>] SENDING PAYLOAD: {auth_payload}"); ws.send(json.dumps(auth_payload))
        print("[✓] Tradier WebSocket Stream Session Authenticated and Channels Armed!")
    else:
        print("[❌] Failed to obtain valid session token. Connection unauthenticated.")

def run_ws_loop():
    print("[*] Starting LiveBot WebSocket listener...")
    while True:
        try:
            ws = websocket.WebSocketApp(
                "wss://ws.tradier.com/v1/markets/events", 
                on_message=on_message, 
                on_open=on_ws_open, on_error=lambda ws, err: print(f"\n[!!!] CRASH TRACE: {err}\n")
            )
            ws.run_forever()
            print("[-] Connection closed. Retrying connection in 3 seconds...")
            time.sleep(3)
        except Exception as e:
            print(f"[-] WS Error: {e}. Reconnecting in 5s...", file=sys.stderr)
            time.sleep(5)

if __name__ == "__main__":
    run_ws_loop()
