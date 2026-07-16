import os
import sys
import json
import requests
import ssl
import websocket
import time
from datetime import datetime
from dotenv import load_dotenv

# --- INTEGRATED: Import All Three Playbooks ---
import src.aapl_playbook as aapl
import src.tsla_playbook as tsla
import src.nvda_playbook as nvda
import src.rivn_playbook as rivn
import src.pltr_playbook as pltr

load_dotenv() # This loads everything from your .env file

# --- INTEGRATED: Robust Dynamic Manifest Path Resolution ---
current_dir = os.path.dirname(os.path.abspath(__file__))

# 1. Search for trading_levels.json (Checks 'src/' first, then falls back to Parent Root)
MANIFEST_PATH = os.path.join(current_dir, 'trading_levels.json')
if not os.path.exists(MANIFEST_PATH):
    MANIFEST_PATH = os.path.join(os.path.dirname(current_dir), 'trading_levels.json')

# 2. Search for macro_state.json (Checks Parent Root first, then falls back to 'src/')
MACRO_STATE_PATH = os.path.join(current_dir, '..', 'macro_state.json')
if not os.path.exists(MACRO_STATE_PATH):
    MACRO_STATE_PATH = os.path.join(current_dir, 'macro_state.json')

if not os.path.exists(MANIFEST_PATH):
    print(f"CRITICAL: Manifest not found at {MANIFEST_PATH}. Please generate it.")
    sys.exit(1)

# Persistent state for atomic file monitoring
LAST_READ_TIME = 0
MASTER_DATA = json.load(open(MANIFEST_PATH, 'r'))

LEVEL_TIMER = {}
LIQUIDITY_HEARTBEAT = {}
TICK_COUNTER = {} 
ACTIVE_TRADES = {} 
LAST_EXIT_TIME = {}
LAST_EXIT_PRICE = {}

# --- INTEGRATED: Multi-Ticker Routing Map ---
PLAYBOOKS = {
    "AAPL": aapl,
    "TSLA": tsla,
    "NVDA": nvda,
    "RIVN": rivn,
    "PLTR": pltr
}

# --- INTEGRATED: Multi-Ticker In-Memory Telemetry Pools ---
TELEMETRY = {
    "AAPL": {"candles_1m": [], "current_candle": None, "cum_volume": 0.0, "cum_pv": 0.0, "current_vwap": 0.0},
    "TSLA": {"candles_1m": [], "current_candle": None, "cum_volume": 0.0, "cum_pv": 0.0, "current_vwap": 0.0},
    "NVDA": {"candles_1m": [], "current_candle": None, "cum_volume": 0.0, "cum_pv": 0.0, "current_vwap": 0.0},
    "RIVN": {"candles_1m": [], "current_candle": None, "cum_volume": 0.0, "cum_pv": 0.0, "current_vwap": 0.0},
    "PLTR": {"candles_1m": [], "current_candle": None, "cum_volume": 0.0, "cum_pv": 0.0, "current_vwap": 0.0}
}

def update_trading_levels_atomic(new_levels):
    """Physically updates trading_levels.json using atomic file replacement."""
    filepath = MANIFEST_PATH
    temp_filepath = f"{filepath}.tmp"
    
    # Write to temp file first
    with open(temp_filepath, 'w') as f:
        json.dump(new_levels, f, indent=4)
        
    # Atomic swap: The OS ensures this is instantaneous
    os.replace(temp_filepath, filepath)
    print("[+] trading_levels.json updated atomically.")

def reload_manifest_if_changed():
    """Checks file metadata and reloads MASTER_DATA if updated on disk."""
    global MASTER_DATA, LAST_READ_TIME
    mtime = os.path.getmtime(MANIFEST_PATH)
    if mtime > LAST_READ_TIME:
        with open(MANIFEST_PATH, 'r') as f:
            MASTER_DATA = json.load(f)
        LAST_READ_TIME = mtime
        print("[*] Detected change in trading levels. Reloading...")

def load_macro_context():
    """Asynchronously reads the macro state from the shared JSON file."""
    if not os.path.exists(MACRO_STATE_PATH):
        return {"macro_regime": "NORMAL", "risk_bias": "NEUTRAL", "operational_directive": "None"}
    try:
        with open(MACRO_STATE_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        return {"macro_regime": "ERR_READ", "risk_bias": "MAX_CAUTION", "operational_directive": "Failed to read macro state."}

def calculate_exits(entry_price):
    p = float(entry_price)
    risk = p * 0.005
    return p - risk, p + (risk * 2), p + (risk * 4)

def send_discord_alert(ticker, action, price, detail="", conviction_data=None):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url: return

    cso_notes = f"\n\n**[CSO CONVICTION MATRIX]**\n• **Conviction:** {conviction_data['conviction']} ({conviction_data['confidence']}% Confidence)\n• **Volume:** {conviction_data.get('volume_status', 'N/A')}\n• **Action:** {conviction_data['action']}\n• **Reasoning:** {conviction_data['notes']}" if conviction_data else ""
    if conviction_data and conviction_data.get('conviction') == "HIGH":
        sl, tp1, tp2 = calculate_exits(price)
        cso_notes += f"\n• **SL:** {sl:.2f} | **TP1:** {tp1:.2f} | **TP2:** {tp2:.2f}"

    payload = {
        "embeds": [{
            "title": f"Harmonized AI Sentry: {action}",
            "color": 16711680 if "REJECTION" in action or "SHORT" in action else (65535 if "PROXIMITY" in action else (16776960 if "CAUTION" in action else 65280)),
            "fields": [
                {"name": "Asset", "value": ticker, "inline": True},
                {"name": "Price", "value": f"{price}", "inline": True},
                {"name": "Detail", "value": detail + cso_notes, "inline": False}
            ]
        }]
    }
    try: requests.post(webhook_url, json=payload)
    except Exception as e: print(f"Alert Error: {e}")

def get_tactical_modifier(ticker, current_price, trade_side):
    asset = MASTER_DATA["levels"].get(ticker, {})
    tactical = asset.get("human_tactical", {})
    modifier = 1.0
    price_f = float(current_price)
    if trade_side == "LONG" and "breakdown_trigger" in tactical:
        trigger = float(tactical["breakdown_trigger"])
        if abs(price_f - trigger) < 1.0: modifier = 0.5
    if "reversal_zone" in tactical:
        reversal_zone = [float(x) for x in tactical.get("reversal_zone", [])]
        if price_f in reversal_zone: modifier = 1.2
    return modifier

def calculate_trade_conviction(ticker, current_price, trade_side, curr_vol, conditions=None):
    if ACTIVE_TRADES.get(ticker, False):
        return {"conviction": "NONE", "confidence": 0, "action": "PASS", "notes": "Trade Active: Locked."}
    
    macro_context = load_macro_context()
    if macro_context.get("risk_bias") == "RISK_OFF_LIQUIDATION" and trade_side == "LONG":
        return {"conviction": "NONE", "confidence": 0, "action": "PASS", "notes": f"BLOCKED BY MACRO SENTINEL: {macro_context.get('operational_directive')}"}
    
    if current_price is None:
        return {"conviction": "NONE", "confidence": 0, "action": "PASS", "notes": "Invalid price data."}
    
    asset = MASTER_DATA["levels"].get(ticker)
    if not asset: return {"conviction": "NONE", "confidence": 0, "action": "PASS", "notes": "No manifest."}
    
    macro = asset.get("algo_macro", {})
    avg_vol = asset.get("avg_volume", 1000)
    vol_ok = curr_vol > (avg_vol * 0.8)
    vol_surge_multiplier = min(max(curr_vol / avg_vol, 1.0), 2.0)
    
    price_f = float(current_price)
    mod = get_tactical_modifier(ticker, price_f, trade_side)
    
    if trade_side == "LONG":
        support_array = macro.get("support", [])
        support = support_array[0] if (isinstance(support_array, list) and len(support_array) > 0) else None
        if support is not None:
            dist = abs(price_f - float(support))
            if dist <= 2.50 and vol_ok:
                conf = int(88 * mod)
                return {"conviction": "HIGH" if conf > 70 else "MEDIUM", "confidence": conf, "action": "EXECUTE", "notes": "Institutional Support Hold."}
                
    return {"conviction": "LOW", "confidence": 20, "action": "PASS", "notes": "Waiting for conviction."}

# --- INTEGRATED: Asset-Specific Active Trade Queries ---
def has_active_position(ticker):
    """Returns True if there is an open trade on the specified ticker."""
    return ACTIVE_TRADES.get(ticker, False)

def execute_order(symbol, ticker, quantity, side):
    """Submits limit or market options executions to sandbox environment."""
    print(f"[*] Dispatching Broker Order for {symbol}: {side.upper()} {quantity} contracts of {ticker}")
    if "buy" in side.lower():
        ACTIVE_TRADES[symbol] = True
    elif "sell" in side.lower():
        ACTIVE_TRADES[symbol] = False

# --- INTEGRATED: Isolated Ticker Candle Accumulation ---
def process_candle_and_vwap_telemetry(ticker, price, vol):
    """Processes ticking events to construct candles and dynamic VWAP per ticker."""
    global TELEMETRY
    now_m = int(time.time() / 60)
    data = TELEMETRY[ticker]
    
    # 1. Update VWAP
    data["cum_volume"] += vol
    data["cum_pv"] += (price * vol)
    if data["cum_volume"] > 0:
         data["current_vwap"] = data["cum_pv"] / data["cum_volume"]
        
    # 2. Update/Rotate 1m candle state
    if data["current_candle"] is None or data["current_candle"]['minute'] != now_m:
        if data["current_candle"] is not None:
            data["candles_1m"].append(data["current_candle"])
            if len(data["candles_1m"]) > 20:
                data["candles_1m"].pop(0)
                
        data["current_candle"] = {
            'minute': now_m,
            'open': price,
            'high': price,
            'low': price,
            'close': price
        }
    else:
        data["current_candle"]['high'] = max(data["current_candle"]['high'], price)
        data["current_candle"]['low'] = min(data["current_candle"]['low'], price)
        data["current_candle"]['close'] = price

# --- INTEGRATED: Multi-Ticker Main Intraday Event Loop ---
def on_market_tick(ticker, current_price, current_vwap, candles_1m):
    """Main execution router evaluated on every new tick per asset."""
    if ticker not in PLAYBOOKS:
        return
        
    playbook = PLAYBOOKS[ticker]
    
    if not has_active_position(ticker):
        # Evaluate Call Entry Setup
        buy_calls, contract_count = playbook.evaluate_call_entry(candles_1m, current_price, current_vwap)
        if buy_calls:
            print(f"[🔥 TRIGGER] {ticker} Bullish Support confirmed. Sizing: {contract_count} contracts.")
            execute_order(ticker, playbook.TICKER_CALL, quantity=contract_count, side="buy_to_open")
            send_discord_alert(ticker, "BUY_TO_OPEN_CALL", current_price, f"Rule matched. Target Contracts: {contract_count}")
            return
            
        # Evaluate Put Entry Setup
        buy_puts, contract_count = playbook.evaluate_put_entry(candles_1m, current_price, current_vwap)
        if buy_puts:
            print(f"[🔥 TRIGGER] {ticker} Bearish Resistance confirmed. Sizing: {contract_count} contracts.")
            execute_order(ticker, playbook.TICKER_PUT, quantity=contract_count, side="buy_to_open")
            send_discord_alert(ticker, "BUY_TO_OPEN_PUT", current_price, f"Rule matched. Target Contracts: {contract_count}")
            return

def on_message(ws, message):
    reload_manifest_if_changed()
    try:
        events = json.loads(message)
        if not isinstance(events, list): events = [events]
        for e in events:
            if e.get("ev") == "T":
                vol, sym, price = e.get("size", 0), e.get("sym"), e.get("price")
                
                # Check active playbook assets
                if sym in PLAYBOOKS:
                    process_candle_and_vwap_telemetry(sym, price, vol)
                    
                    # Package up full 1m candles including the currently forming one
                    data = TELEMETRY[sym]
                    candles_to_eval = data["candles_1m"] + ([data["current_candle"]] if data["current_candle"] else [])
                    on_market_tick(sym, price, data["current_vwap"], candles_to_eval)
                
                # Check legacy indicators for subscription assets
                if sym in MASTER_DATA["levels"]:
                    conv = calculate_trade_conviction(sym, price, "LONG", vol)
                    if conv['action'] == "EXECUTE": 
                        ACTIVE_TRADES[sym] = True
                        send_discord_alert(sym, "EXECUTION", price, "Signal triggered", conv)
    except Exception as e: print(f"DEBUG: Message Error: {e}", file=sys.stderr)

def get_fresh_session_id():
    token = os.getenv("TRADIER_TOKEN")
    response = requests.post(
        'https://api.tradier.com/v1/markets/events/session', 
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json'
        },
        data={}  # This explicitly sets Content-Length: 0
    )
    if response.status_code != 200:
        print(f"DEBUG: API returned {response.status_code}: {response.text}")
        raise Exception("Failed to fetch session ID")
        
    return response.json()['stream']['sessionid']

def on_open(ws):
    print("### Authenticating with Tradier... ###")
    try:
        session_id = get_fresh_session_id()
        payload = {
            # Subscribing to MSFT, SPY, AAPL, TSLA, and NVDA to feed the execution matrix
            "symbols": ["MSFT", "SPY", "AAPL", "TSLA", "NVDA", "RIVN", "PLTR"], 
            "filter": ["trade"], 
            "sessionid": session_id, 
            "linebreak": True
        }
        ws.send(json.dumps(payload))
        print("### Subscription sent successfully ###")
    except Exception as e:
        print(f"Auth Failed: {e}")

print("Harmonized AI LiveBot v2.2 Active with Atomic Manifest Reloading.")

if __name__ == "__main__":
    # Ensure URL is correct
    ws = websocket.WebSocketApp(
        "wss://ws.tradier.com/v1/markets/events", 
        on_message=on_message,
        on_open=on_open
    )
    ws.run_forever()
