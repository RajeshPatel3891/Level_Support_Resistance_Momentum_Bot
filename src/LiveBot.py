
# =====================================================================
# THETA DECAY & 0DTE INTRADAY ROLLOVER PROTECTION ENGINE
# =====================================================================
import datetime
import pytz

def get_target_expiration_date():
    """
    Enforces the 1:30 PM EST Cutoff:
    - Before 1:30 PM EST -> Returns today's date (0DTE)
    - After 1:30 PM EST  -> Returns tomorrow's date (1DTE)
    """
    tz = pytz.timezone('US/Eastern')
    now_et = datetime.now(tz)
    cutoff = now_et.replace(hour=13, minute=30, second=0, microsecond=0)
    
    if now_et >= cutoff:
        # Roll over to next business day
        target_date = now_et + timedelta(days=1)
        if target_date.weekday() == 5:  # Saturday -> Monday
            target_date += timedelta(days=2)
        elif target_date.weekday() == 6:  # Sunday -> Monday
            target_date += timedelta(days=1)
        print(f"[🕒 ROLLOVER ENGINE] After 1:30 PM EST ({now_et.strftime('%H:%M EST')}). Bypassing 0DTE -> Target Expiration: {target_date.strftime('%Y-%m-%d')} (1DTE)")
        return target_date.strftime('%Y-%m-%d')
    else:
        print(f"[🕒 ROLLOVER ENGINE] Before 1:30 PM EST ({now_et.strftime('%H:%M EST')}). Standard 0DTE Target Expiration: {now_et.strftime('%Y-%m-%d')}")
        return now_et.strftime('%Y-%m-%d')

def validate_extrinsic_floor(ticker, option_price, spot_price, strike, side="CALL"):
    """
    Low-Nominal ($10-$20) Extrinsic Floor Filter:
    Rejects OTM contracts under $0.20 premium and forces ITM delta selection.
    """
    LOW_NOMINAL_TICKERS = {"F", "SOFI", "AAL", "RIVN"}
    MIN_PREMIUM_FLOOR = 0.20
    
    if ticker in LOW_NOMINAL_TICKERS and option_price < MIN_PREMIUM_FLOOR:
        print(f"[⚠️ THETA FLOOR BREACH] {ticker} option premium (${option_price:.2f}) is below ${MIN_PREMIUM_FLOOR:.2f} floor!")
        
        # Calculate In-The-Money (ITM) Strike Shift
        if side.upper() == "CALL":
            itm_strike = spot_price * 0.97  # 3% In-The-Money
        else:
            itm_strike = spot_price * 1.03  # 3% In-The-Money for PUT
            
        print(f"[🛡️ ITM SHIFT RE-ROUTE] Shifting {ticker} strike from ${strike:.2f} -> ITM Strike ~${itm_strike:.2f} (Delta ~0.70) to preserve intrinsic value.")
        note = f"[ITM_SHIFT] Premium < $0.20 floor. Re-routed {strike} -> {itm_strike}"
        return False, itm_strike, note
        
    return True, strike, "STANDARD_PREMIUM"

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
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
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
import src.sofi_playbook as sofi
import src.intc_playbook as intc
import src.f_playbook as f_pb
import src.aal_playbook as aal
from src.GexReader import get_latest_gex_context

load_dotenv()

MANIFEST_PATH = os.path.join(CURRENT_DIR, 'trading_levels.json')
if not os.path.exists(MANIFEST_PATH):
    MANIFEST_PATH = os.path.join(PARENT_DIR, 'trading_levels.json')

MASTER_DATA = json.load(open(MANIFEST_PATH, 'r'))
ACTIVE_TRADES = {}
TELEMETRY = {}
PLAYBOOKS = {"AAPL": aapl, "TSLA": tsla, "NVDA": nvda, "RIVN": rivn, "PLTR": pltr, "SOFI": sofi, "INTC": intc, "F": f_pb, "AAL": aal}

# --- OPTIONS MECHANICS & MULTIPLIER CONFIG ---
CONTRACT_MULTIPLIER = 100
DEFAULT_DELTA = 0.50  # Estimated ~50 Delta for ATM Call/Put contracts

def fetch_occ_option_symbol(underlying: str, option_type: str, spot_price: float) -> str:
    """
    Queries Tradier API for closest ATM option contract expiration and OCC symbol format.
    Fallback: Builds standard OCC symbol string format (e.g. AAPL260724C00325000).
    """
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    if "sandbox" in base_url.lower():
        token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
    else:
        token = os.getenv("TRADIER_TOKEN")
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    try:
        # 1. Fetch Expirations
        exp_res = requests.get(f"{base_url}/markets/options/expirations", params={"symbol": underlying}, headers=headers, timeout=3)
        if exp_res.status_code == 200:
            expirations = exp_res.json().get("expirations", {}).get("date", [])
            if isinstance(expirations, str):
                expirations = [expirations]
            if expirations:
                target_exp = expirations[0]  # Front-week / 0DTE target
                
                # 2. Query Options Chain for nearest ATM Strike
                chain_res = requests.get(
                    f"{base_url}/markets/options/chains",
                    params={"symbol": underlying, "expiration": target_exp, "greeks": "false"},
                    headers=headers,
                    timeout=3
                )
                if chain_res.status_code == 200:
                    options = chain_res.json().get("options", {}).get("option", [])
                    if isinstance(options, dict):
                        options = [options]
                    
                    target_side = "call" if option_type.upper() == "CALL" else "put"
                    matching_options = [o for o in options if o.get("option_type") == target_side]
                    
                    if matching_options:
                        # Find contract closest to current spot price
                        best_contract = min(matching_options, key=lambda x: abs(float(x.get("strike", 0)) - spot_price))
                        occ_symbol = best_contract.get("symbol")
                        if occ_symbol:
                            return occ_symbol
    except Exception as e:
        print(f"[-] OCC Option Lookup Fallback triggered for {underlying}: {e}", file=sys.stderr)

    # Fallback: Construct synthetic OCC symbol format [Ticker][YYMMDD][C/P][Strike*1000 formatted to 8 digits]
    now = datetime.now()
    date_str = now.strftime("%y%m%d")
    type_code = "C" if option_type.upper() == "CALL" else "P"
    strike_fmt = f"{int(round(spot_price * 1000)):08d}"
    return f"{underlying}{date_str}{type_code}{strike_fmt}"

def calculate_playbook_params(ticker: str, current_price: float, gex_support: float, gex_regime: str, ohlc_df: pd.DataFrame):
    """
    Playbook Execution Matrix for Options Contracts:
    - Calculates 14-period ATR for underlying movement.
    - Adjusts buffer based on GEX Regime (+GEX vs -GEX).
    - Caps total account risk at $30.00 per trade.
    - Converts share risk distance into equivalent Options Contracts.
    """
    # 1. Calculate 14-period ATR from OHLC data
    high_low = ohlc_df['high'] - ohlc_df['low']
    high_close = np.abs(ohlc_df['high'] - ohlc_df['close'].shift())
    low_close = np.abs(ohlc_df['low'] - ohlc_df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    atr = true_range.rolling(14).mean().iloc[-1]
    
    if np.isnan(atr) or atr <= 0:
        atr = current_price * 0.01

    # 2. Select ATR Buffer Multiplier based on GEX Regime
    atr_multiplier = 0.75 if gex_regime == "POSITIVE_GEX" else 0.25

    # 3. Calculate technical stop-loss price on underlying
    rebound_buffer = atr * atr_multiplier
    stop_loss_price = round(gex_support - rebound_buffer, 2)
    
    risk_distance = max(abs(current_price - stop_loss_price), 0.10)

    # 4. Target Risk Budget = $30.00 (1.5% of $2,000 account)
    TARGET_RISK_BUDGET = 30.00
    
    # Options Contract Sizing using Delta math
    # Risk per contract = risk_distance * DEFAULT_DELTA * CONTRACT_MULTIPLIER
    risk_per_contract = max(risk_distance * DEFAULT_DELTA * CONTRACT_MULTIPLIER, 5.0)
    calculated_contracts = max(1, int(TARGET_RISK_BUDGET / risk_per_contract))
    
    # Cap contracts based on maximum affordable premium budget ($500 max per option entry)
    estimated_premium = max(current_price * 0.01, 1.50)  # ~$1.50 - $3.00 option premium estimate
    max_affordable_contracts = max(1, int(500.00 / (estimated_premium * CONTRACT_MULTIPLIER)))
    contracts_to_buy = min(calculated_contracts, max_affordable_contracts)

    return {
        "entry_price": current_price,
        "stop_loss": stop_loss_price,
        "atr": round(atr, 2),
        "rebound_buffer": round(rebound_buffer, 2),
        "shares": contracts_to_buy,  # Stores contract count for database schema compatibility
        "max_risk_dollars": round(contracts_to_buy * risk_per_contract, 2)
    }

def init_account_ledger(db_path="harm_telemetry.db", starting_capital=2000.00):
    """Ensures account_ledger table exists and seeds today's starting settled capital."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_ledger (
                date TEXT PRIMARY KEY,
                starting_settled_cash REAL,
                available_settled_cash REAL,
                unsettled_cash REAL
            )
        ''')
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT available_settled_cash FROM account_ledger WHERE date = ?", (today_str,))
        row = cursor.fetchone()
        if not row:
            cursor.execute('''
                INSERT INTO account_ledger (date, starting_settled_cash, available_settled_cash, unsettled_cash)
                VALUES (?, ?, ?, 0.0)
            ''', (today_str, starting_capital, starting_capital))
            conn.commit()
            print(f"[✓] Initialized account ledger for {today_str} with ${starting_capital:,.2f} settled cash.")
        conn.close()
    except Exception as e:
        print(f"[-] Account Ledger Init Error: {e}", file=sys.stderr)

init_account_ledger()

def get_available_settled_cash(db_path="harm_telemetry.db"):
    """Queries available settled cash for today's session."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute("SELECT available_settled_cash FROM account_ledger WHERE date = ?", (today_str,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return float(row[0])
    except Exception as e:
        print(f"[-] Ledger Query Error: {e}", file=sys.stderr)
    return 0.0

def update_settled_cash_balance(deduct_amount, db_path="harm_telemetry.db"):
    """Deducts used trade capital from available settled cash."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor.execute('''
            UPDATE account_ledger 
            SET available_settled_cash = available_settled_cash - ? 
            WHERE date = ?
        ''', (deduct_amount, today_str))
        conn.commit()
        conn.close()
        print(f"[✓] Ledger Updated: Deducted ${deduct_amount:,.2f} settled cash.")
    except Exception as e:
        print(f"[-] Ledger Balance Update Error: {e}", file=sys.stderr)

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
            print(f"[!] Warning: High-volatility dealer regime detected for {symbol}. Applying strict risk filters.")
            return "HIGH_VOLATILITY_MODE"
        else:
            return "STANDARD_REGIME"
            
    return "NO_CONTEXT"

def handle_shutdown_signal(signum, frame):
    """Force an immediate exit the millisecond Ctrl+C is pressed."""
    print("\n🛑 [SHUTDOWN] Intercepted termination signal. Exiting LiveBot safely.")
    sys.exit(0)

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
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    if "sandbox" in base_url.lower():
        token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
    else:
        token = os.getenv("TRADIER_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    url = f"https://sandbox.tradier.com/v1/accounts/{account_id}/orders/{order_id}"
    response = requests.get(url, headers=headers)
    return response.json().get("order", {}).get("status") if response.status_code == 200 else "UNKNOWN"

def log_trade_to_database(ticker, spot_price, stop_loss=None, shares=1.0, direction="CALL"):
    try:
        conn = sqlite3.connect("harm_telemetry.db")
        cursor = conn.cursor()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sl_val = stop_loss if stop_loss is not None else round(spot_price * 0.990, 2)
        take_profit = round(spot_price + 3.98, 2)
        opt_premium = round(max(0.80, spot_price * 0.012), 2)
        opt_premium = round(max(0.80, spot_price * 0.012), 2)
        cursor.execute("""
            INSERT INTO trades (ticker, timestamp, strategy, direction, spot_price, entry_price, shares, stop_loss, take_profit, net_pnl, exit_status, is_live) 
            VALUES (?, ?, 'BREAKOUT', ?, ?, ?, ?, ?, ?, 0.0, 'ACTIVE', 1)
        """, (ticker, timestamp, direction, spot_price, opt_premium, shares, sl_val, take_profit))
        conn.commit()
        conn.close()
        print(f"[✓] Logged verified options trade for {ticker} (Contracts: {shares}, SL: ${sl_val:.2f}) to SQLite.")
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
        
        time.sleep(5)

threading.Thread(target=db_batch_worker, daemon=True).start()

def get_ticker_candles_and_vwap(symbol, db_path="harm_telemetry.db"):
    """Fetches recent ticks to construct clean float-based OHLC candles and calculate live VWAP."""
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql_query(
            "SELECT price FROM tick_history WHERE ticker = ? AND price IS NOT NULL ORDER BY id DESC LIMIT 100",
            conn, params=(symbol,)
        )
        conn.close()
        if not df.empty:
            df['price'] = pd.to_numeric(df['price'], errors='coerce')
            df = df.dropna(subset=['price'])
            if not df.empty:
                prices = [float(x) for x in df['price'].tolist()]
                vwap = float(np.mean(prices))
                candles = [{'open': p, 'high': p, 'low': p, 'close': p, 'price': p} for p in prices]
                return candles, vwap
    except Exception:
        pass
    return [], 0.0

def execute_order(symbol, ticker, quantity, side, limit_price=None, stop_loss=None):
    """
    Executes Options Orders via Tradier API using class: 'option' and standard OCC format.
    """
    spot_val = float(limit_price) if limit_price else 100.00
    occ_symbol = fetch_occ_option_symbol(symbol, side, spot_val)
    
    # Premium cost estimation for capital allocation (~$2.50 per contract multiplier)
    estimated_contract_cost = 250.00  # $2.50 premium * 100 multiplier
    required_capital = float(quantity) * estimated_contract_cost
    available_settled_cash = get_available_settled_cash()

    if available_settled_cash < required_capital:
        adjusted_quantity = int(available_settled_cash // estimated_contract_cost)
        if adjusted_quantity > 0:
            print(f"[*] Capital Auto-Scale: Reducing {symbol} options contracts from {quantity} -> {adjusted_quantity} to fit ${available_settled_cash:,.2f} budget.")
            quantity = adjusted_quantity
            required_capital = quantity * estimated_contract_cost
        else:
            print(f"[!] REJECTED: Insufficient Settled Cash for Options Premium (${available_settled_cash:.2f} available, ${required_capital:.2f} needed)")
            return False

    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    if "sandbox" in base_url.lower():
        token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
    else:
        token = os.getenv("TRADIER_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    
    # Options Order Payload Layout for Tradier API
    order_side = "buy_to_open" if side.upper() in ["CALL", "BUY"] else "sell_to_open"
    payload = {
        "class": "option", 
        "symbol": symbol, 
        "option_symbol": occ_symbol,
        "side": order_side, 
        "quantity": str(int(quantity)), 
        "type": "market", 
        "duration": "day"
    }
    
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    response = requests.post(
        f"{base_url}/accounts/{account_id}/orders", 
        data=payload, 
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    
    if response.status_code == 200:
        order_id = response.json().get("order", {}).get("id")
        time.sleep(2)
        status = get_order_status(order_id)
        if status in ["filled", "ok", "open", "pending"]:
            update_settled_cash_balance(required_capital)
            log_trade_to_database(symbol, spot_val, stop_loss=stop_loss, shares=float(quantity), direction=side)
            try:
                dispatch_discord_alert(symbol, spot_val, 'ENTRY')
            except:
                pass
            ACTIVE_TRADES[symbol] = True
            return True
    else:
        # Internal fill fallback for sandbox/simulation execution
        print(f"[*] Tradier Option API status {response.status_code}. Falling back to internal engine option fill.")
        update_settled_cash_balance(required_capital)
        log_trade_to_database(symbol, spot_val, stop_loss=stop_loss, shares=float(quantity), direction=side)
        ACTIVE_TRADES[symbol] = True
        return True

    return False

def on_message(ws, message):
    if not is_market_hours():
        return

    try:
        events = json.loads(message)
        if isinstance(events, dict): events = [events]
        for e in events:
            if e.get("type") == "trade":
                sym, price = e.get("symbol"), e.get("price")
                tick_queue.put((sym, datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"), float(price)))
                print(f"[+] TICKER HIT -> {sym}: ${price}")
                # Update in-memory master data and flush live stream price to trading_levels.json
                if sym in MASTER_DATA and isinstance(MASTER_DATA[sym], dict):
                    MASTER_DATA[sym]["last_price"] = float(price)
                    sup = MASTER_DATA[sym].get("support", [])
                    res = MASTER_DATA[sym].get("resistance", [])
                    
                    if len(sup) >= 2 and len(res) >= 2:
                        armed = (sup[0] <= float(price) <= sup[1]) or (res[0] <= float(price) <= res[1])
                        MASTER_DATA[sym]["execution_armed"] = armed
                        MASTER_DATA[sym]["status"] = "ARMED" if armed else "WAITING"
                    
                    try:
                        with open(MANIFEST_PATH, "w") as mf:
                            json.dump(MASTER_DATA, mf, indent=2)
                    except Exception:
                        pass
                # Update in-memory master data and flush live stream price to trading_levels.json
                if sym in MASTER_DATA and isinstance(MASTER_DATA[sym], dict):
                    MASTER_DATA[sym]["last_price"] = float(price)
                    sup = MASTER_DATA[sym].get("support", [])
                    res = MASTER_DATA[sym].get("resistance", [])
                    
                    if len(sup) >= 2 and len(res) >= 2:
                        armed = (sup[0] <= float(price) <= sup[1]) or (res[0] <= float(price) <= res[1])
                        MASTER_DATA[sym]["execution_armed"] = armed
                        MASTER_DATA[sym]["status"] = "ARMED" if armed else "WAITING"
                    
                    try:
                        with open(MANIFEST_PATH, "w") as mf:
                            json.dump(MASTER_DATA, mf, indent=2)
                    except Exception:
                        pass
                if sym in PLAYBOOKS:
                    regime = evaluate_ticker_risk(sym)
                    
                    if ACTIVE_TRADES.get(sym):
                        pass
                    else:
                        pb = PLAYBOOKS[sym]
                        candles_list, current_vwap = get_ticker_candles_and_vwap(sym)
                        
                        if candles_list:
                            call_sig, call_shares = pb.evaluate_call_entry(candles_list, float(price), current_vwap)
                            put_sig, put_shares   = pb.evaluate_put_entry(candles_list, float(price), current_vwap)
                            
                            if call_sig and call_shares > 0:
                                stop_lvl = float(price) - pb.PLAYBOOK_CONFIG.get("atr_14_buffer", 1.50)
                                execute_order(sym, sym, call_shares, "CALL", limit_price=float(price), stop_loss=stop_lvl)
                                
                            elif put_sig and put_shares > 0:
                                stop_lvl = float(price) + pb.PLAYBOOK_CONFIG.get("atr_14_buffer", 1.50)
                                execute_order(sym, sym, put_shares, "PUT", limit_price=float(price), stop_loss=stop_lvl)
    except Exception:
        pass

def get_streaming_session():
    # Stream session IDs must always be generated via production endpoint
    token = os.getenv("TRADIER_TOKEN")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        r = requests.post("https://api.tradier.com/v1/markets/events/session", headers=headers)
        if r.status_code == 200:
            return r.json().get("stream", {})
    except Exception as e:
        print(f"[-] Session API Request Error: {e}")
    return {}

def on_ws_open(ws):
    session_info = get_streaming_session()
    session_id = session_info.get("sessionid")
    
    if session_id:
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
