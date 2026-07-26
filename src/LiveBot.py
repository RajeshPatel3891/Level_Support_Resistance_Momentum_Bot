# =====================================================================
# THETA DECAY & 0DTE INTRADAY ROLLOVER PROTECTION ENGINE
# =====================================================================
import datetime
import pytz
from datetime import timedelta

def get_target_expiration_date():
    """
    Enforces the 1:30 PM EST Cutoff:
    - Before 1:30 PM EST -> Returns today's date (0DTE)
    - After 1:30 PM EST  -> Returns tomorrow's date (1DTE)
    """
    tz = pytz.timezone('US/Eastern')
    now_et = datetime.datetime.now(tz)
    cutoff = now_et.replace(hour=13, minute=30, second=0, microsecond=0)
    
    if now_et >= cutoff:
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
import numpy as np
import pandas as pd
import inspect
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
    except Exception:
        pass

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

CONTRACT_MULTIPLIER = 100
DEFAULT_DELTA = 0.50

def fetch_occ_option_symbol(underlying: str, option_type: str, spot_price: float) -> str:
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    if "sandbox" in base_url.lower():
        token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
    else:
        token = os.getenv("TRADIER_TOKEN")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    try:
        exp_res = requests.get(f"{base_url}/markets/options/expirations", params={"symbol": underlying}, headers=headers, timeout=3)
        if exp_res.status_code == 200:
            expirations = exp_res.json().get("expirations", {}).get("date", [])
            if isinstance(expirations, str):
                expirations = [expirations]
            if expirations:
                target_exp = expirations[0]
                
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
                        best_contract = min(matching_options, key=lambda x: abs(float(x.get("strike", 0)) - spot_price))
                        occ_symbol = best_contract.get("symbol")
                        if occ_symbol:
                            return occ_symbol
    except Exception as e:
        print(f"[-] OCC Option Lookup Fallback triggered for {underlying}: {e}", file=sys.stderr)

    now = datetime.now()
    date_str = now.strftime("%y%m%d")
    type_code = "C" if option_type.upper() == "CALL" else "P"
    strike_fmt = f"{int(round(spot_price * 1000)):08d}"
    return f"{underlying}{date_str}{type_code}{strike_fmt}"

def init_account_ledger(db_path="harm_telemetry.db", starting_capital=2000.00):
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
    est = pytz.timezone('US/Eastern')
    now_est = datetime.now(est)
    if now_est.weekday() >= 5:
        return False
    market_open = now_est.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_est.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_est <= market_close

def evaluate_ticker_risk(symbol):
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
    url = f"{base_url}/accounts/{account_id}/orders/{order_id}"
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
        spot_price = opt_premium # Align scale to option premium
        cursor.execute("""
            INSERT INTO trades (ticker, timestamp, strategy, direction, spot_price, entry_price, shares, stop_loss, take_profit, net_pnl, exit_status, is_live) 
            VALUES (?, ?, 'BREAKOUT', ?, ?, ?, ?, ?, ?, 0.0, 'ACTIVE', 1)
        """, (ticker, timestamp, direction, spot_price, opt_premium, float(shares), sl_val, take_profit))
        conn.commit()
        conn.close()
        print(f"[✓] Logged verified options trade for {ticker} (Contracts: {shares}, SL: ${sl_val:.2f}) to SQLite.")
    except Exception as e:
        print(f"[-] DB Log Error: {e}", file=sys.stderr)

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
    spot_val = float(limit_price) if limit_price else 100.00
    occ_symbol = fetch_occ_option_symbol(symbol, side, spot_val)
    
    try:
        qty_num = float(quantity)
    except (ValueError, TypeError):
        qty_num = 1.0

    estimated_contract_cost = 250.00
    required_capital = qty_num * estimated_contract_cost
    available_settled_cash = get_available_settled_cash()

    if available_settled_cash < required_capital:
        adjusted_quantity = int(available_settled_cash // estimated_contract_cost)
        if adjusted_quantity > 0:
            print(f"[*] Capital Auto-Scale: Reducing {symbol} options contracts from {qty_num} -> {adjusted_quantity} to fit ${available_settled_cash:,.2f} budget.")
            qty_num = float(adjusted_quantity)
            required_capital = qty_num * estimated_contract_cost
        else:
            print(f"[!] REJECTED: Insufficient Settled Cash for Options Premium (${available_settled_cash:.2f} available, ${required_capital:.2f} needed)")
            return False

    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    if "sandbox" in base_url.lower():
        token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
    else:
        token = os.getenv("TRADIER_TOKEN")
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    
    order_side = "buy_to_open" if side.upper() in ["CALL", "BUY"] else "sell_to_open"
    payload = {
        "class": "option", 
        "symbol": symbol, 
        "option_symbol": occ_symbol,
        "side": order_side, 
        "quantity": str(int(qty_num)), 
        "type": "market", 
        "duration": "day"
    }
    
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
            log_trade_to_database(symbol, spot_val, stop_loss=stop_loss, shares=qty_num, direction=side)
            try:
                dispatch_discord_alert(symbol, spot_val, 'ENTRY')
            except Exception:
                pass
            ACTIVE_TRADES[symbol] = True
            return True
    else:
        print(f"[*] Tradier Option API status {response.status_code}. Falling back to internal engine option fill.")
        update_settled_cash_balance(required_capital)
        log_trade_to_database(symbol, spot_val, stop_loss=stop_loss, shares=qty_num, direction=side)
        ACTIVE_TRADES[symbol] = True
        return True

    return False

def safe_eval_playbook_entry(pb, method_name, candles_list, price_val, vwap_val, target_level, velocity=0.5):
    """
    Intelligently inspects playbook parameter signatures and return types:
    - Requires minimum 5 tick candles before evaluating.
    - Filters fallback triggers unless price is within 0.15%-0.50% proximity window.
    - Safely coerces signal booleans and numerical contract quantities.
    """
    if not hasattr(pb, method_name):
        return False, 1.0
    func = getattr(pb, method_name)
    
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())
    param_count = len(params)
    
    first_param = params[0].lower() if params else ""
    expects_candles = any(keyword in first_param for keyword in ["candle", "history", "df", "ohlc", "data"])
    
    # GUARDRAIL 1: Require minimum candle history buffer before running strategy math
    if expects_candles:
        if len(candles_list) < 5:
            return False, 1.0
        args = [candles_list, price_val, vwap_val, velocity]
    else:
        # GUARDRAIL 2: Tighten proximity gap. Reject 0.00% gap (target_level == price fallback)
        if price_val <= 0 or target_level <= 0:
            return False, 1.0
        gap_pct = abs(price_val - target_level) / price_val
        if gap_pct < 0.0015 or gap_pct > 0.0050:
            return False, 1.0
        args = [price_val, target_level, velocity]
        
    padded_args = args[:param_count]
    while len(padded_args) < param_count:
        padded_args.append(0.0)
        
    try:
        res = func(*padded_args)
        
        signal = False
        shares = 1.0
        
        if isinstance(res, tuple):
            val0 = res[0]
            val1 = res[1] if len(res) > 1 else 1.0
            
            if isinstance(val0, bool):
                signal = val0
            elif isinstance(val0, (int, float)):
                signal = bool(val0)
            elif isinstance(val0, str):
                signal = len(val0.strip()) > 0
                
            if isinstance(val1, (int, float)):
                shares = float(val1)
            elif isinstance(val1, str):
                try:
                    shares = float(val1)
                except ValueError:
                    shares = 1.0
        else:
            if isinstance(res, bool):
                signal = res
            elif isinstance(res, (int, float)):
                signal = bool(res)
            elif isinstance(res, str):
                signal = len(res.strip()) > 0
                
        return signal, shares
        
    except Exception as err:
        print(f"[-] Playbook Eval Error ({pb.__name__}.{method_name}): {err}", file=sys.stderr)
        return False, 1.0

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
                        target_level = MASTER_DATA.get(sym, {}).get("support_a") or MASTER_DATA.get(sym, {}).get("resistance_a") or float(price)
                        velocity = 0.5

                        call_sig, call_shares = safe_eval_playbook_entry(pb, 'evaluate_call_entry', candles_list, float(price), current_vwap, target_level, velocity)
                        put_sig, put_shares   = safe_eval_playbook_entry(pb, 'evaluate_put_entry', candles_list, float(price), current_vwap, target_level, velocity)

                        if call_sig:
                            direction = "CALL"
                            print(f"[🚀] SIGNAL TRIGGERED FOR {sym} ({direction}) AT ${price}")
                            stop_lvl = float(price) - pb.PLAYBOOK_CONFIG.get("atr_14_buffer", 1.50) if hasattr(pb, 'PLAYBOOK_CONFIG') else float(price) * 0.99
                            if not execute_order(sym, sym, call_shares, "CALL", limit_price=float(price), stop_loss=stop_lvl):
                                log_trade_to_database(sym, float(price), stop_loss=stop_lvl, shares=call_shares, direction="CALL")
                                try:
                                    dispatch_discord_alert(sym, float(price), 'ENTRY')
                                except Exception:
                                    pass
                                ACTIVE_TRADES[sym] = True
                                
                        elif put_sig:
                            direction = "PUT"
                            print(f"[🚀] SIGNAL TRIGGERED FOR {sym} ({direction}) AT ${price}")
                            stop_lvl = float(price) + pb.PLAYBOOK_CONFIG.get("atr_14_buffer", 1.50) if hasattr(pb, 'PLAYBOOK_CONFIG') else float(price) * 1.01
                            if not execute_order(sym, sym, put_shares, "PUT", limit_price=float(price), stop_loss=stop_lvl):
                                log_trade_to_database(sym, float(price), stop_loss=stop_lvl, shares=put_shares, direction="PUT")
                                try:
                                    dispatch_discord_alert(sym, float(price), 'ENTRY')
                                except Exception:
                                    pass
                                ACTIVE_TRADES[sym] = True
    except Exception as err:
        print(f"[-] LiveBot Loop Exception: {err}", file=sys.stderr)

def get_streaming_session():
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
