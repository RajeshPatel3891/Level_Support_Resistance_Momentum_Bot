import os
import sys
import json
import time
import random
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Try importing official Alpaca SDK components for Trading & WebSockets
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderType

# Load environment variables
load_dotenv()

# --- SYSTEM DIRECTORY PATH RESOLUTION ---
current_dir = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(current_dir)
MANIFEST_PATH = os.path.join(ROOT_DIR, 'trading_levels.json')
MACRO_STATE_PATH = os.path.join(ROOT_DIR, 'macro_state.json')

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [PRODUCER] {msg}", flush=True)

if not os.path.exists(MANIFEST_PATH):
    log_msg(f"CRITICAL: Manifest not found at {MANIFEST_PATH}. Ensure trading_levels.json exists.")
    sys.exit(1)

# Core State Manifests
MASTER_DATA = json.load(open(MANIFEST_PATH, 'r'))
WATCHLIST = list(MASTER_DATA.get("levels", {}).keys())
ACTIVE_TRADES = {}  # Preserved global tracking state

# --- INITIALIZE AUTHENTICATED TRADING CLIENT ---
API_KEY = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
IS_PAPER = os.getenv("APCA_IS_PAPER", "true").lower() == "true"

trading_client = None
if API_KEY and SECRET_KEY:
    try:
        trading_client = TradingClient(api_key=API_KEY, secret_key=SECRET_KEY, paper=IS_PAPER)
        log_msg(f"Trading Client successfully initialized in [{'PAPER' if IS_PAPER else 'LIVE'}] mode.")
    except Exception as e:
        log_msg(f"Failed to initialize Alpaca Trading Client: {e}")

# --- THE ADVERSE-SELECTION DEFENSE ENVELOPE ---
def submit_smart_order(symbol: str, qty: float, limit_price: float, side: OrderSide = OrderSide.BUY):
    """
    Submits a strict Limit Order with IOC (Immediate or Cancel).
    This forces the trade to fill only at YOUR price or better, 
    and aborts the order instantly if it's not immediately available.
    """
    if not trading_client:
        log_msg("[🛡️] Order Execution Aborted: Trading Client not initialized (No API keys).")
        return None
        
    order_data = LimitOrderRequest(
        symbol=symbol,
        qty=qty,
        side=side,
        type=OrderType.LIMIT,
        time_in_force=TimeInForce.IOC,  # THE KEY: Fill immediately at limit or cancel instantly
        limit_price=limit_price
    )
    
    try:
        order = trading_client.submit_order(order_data=order_data)
        log_msg(f"[✓] Smart Limit IOC Order submitted! ID: {order.id} | Status: {order.status}")
        return order
    except Exception as e:
        log_msg(f"[🛡️] Order Execution Aborted: {e}")
        return None

def load_macro_context():
    """Reads active background sentiment contexts written by the CSO Sentinel Daemon."""
    if not os.path.exists(MACRO_STATE_PATH):
        return {"macro_regime": "NORMAL", "risk_bias": "NEUTRAL", "operational_directive": "None"}
    try:
        with open(MACRO_STATE_PATH, 'r') as f:
            return json.load(f)
    except Exception:
        return {"macro_regime": "ERR", "risk_bias": "CAUTION", "operational_directive": "Error reading state."}

# ==========================================================
# MODE A: REAL-TIME ALPACA WEBSOCKET STREAM
# ==========================================================
async def start_realtime_websocket_stream(api_key, secret_key):
    """
    Connects to Alpaca's live SIP/IEX data feed using alpaca-py.
    Streams actual 1-minute bars at standard market pace.
    """
    try:
        from alpaca.data.live import StockDataStream
    except ImportError:
        log_msg("[!] alpaca-py SDK missing in current environment. Pivoting to local simulation...")
        run_simulation_loop()
        return

    log_msg(f"Connecting to Alpaca Live Market Data Socket for watchlist: {WATCHLIST}...")
    stream = StockDataStream(api_key, secret_key)
    
    async def bar_handler(data):
        """Processes incoming real-time minute bars and formats them for Sentry."""
        bar_tick = {
            "symbol": data.symbol,
            "close": float(data.close),
            "volume": float(data.volume),
            "timestamp": data.timestamp.isoformat()
        }
        # Output unbuffered to stdout so MasterSentry.py captures it instantly
        print(f"BAR_TICK_DATA: {json.dumps(bar_tick)}", flush=True)

    try:
        # Subscribe to standard 1-minute bars for your target assets
        stream.subscribe_bars(bar_handler, *WATCHLIST)
        await stream._run_forever()
    except Exception as e:
        log_msg(f"[!] Live connection error: {e}. Falling back to simulation.")
        run_simulation_loop()

# ==========================================================
# MODE B: HIGH-FIDELITY SIMULATION MODE (Configurable Flow)
# ==========================================================
def run_simulation_loop():
    """
    Simulates high-fidelity intraday equity bars. Walks target stocks up and down
    across technical breakout triggers and reversal zones.
    
    Toggles:
    - SIM_INTERVAL_SECONDS (Default: 30) : Customize tick generation spacing.
    - SIM_ALL_SIMULTANEOUS (Default: False): True matches legacy parallel ticker spam.
    """
    sim_interval = int(os.getenv("SIM_INTERVAL_SECONDS", "30"))
    sim_all_simultaneous = os.getenv("SIM_ALL_SIMULTANEOUS", "False").lower() in ("true", "1", "yes")

    if sim_all_simultaneous:
        log_msg(f"Initiating High-Fidelity Intraday Simulation Loop (Fast Multi-Ticker {sim_interval}s Intervals)...")
    else:
        log_msg(f"Initiating High-Fidelity Intraday Simulation Loop (Relaxed Single-Ticker {sim_interval}s Intervals)...")
    
    levels_config = MASTER_DATA.get("levels", {})
    symbol_states = {}
    
    # Anchor the initial asset price frames slightly below their configured triggers
    for symbol, cfg in levels_config.items():
        tactical = cfg.get("human_tactical", {})
        trigger = tactical.get("breakout_trigger", 250.0)
        reversal = tactical.get("reversal_zone", [trigger - 5.0, trigger - 4.0])
        
        symbol_states[symbol] = {
            "price": trigger - 1.5,
            "trigger": trigger,
            "reversal_low": min(reversal),
            "reversal_high": max(reversal),
            "step": 0,
            "prev_vol": 1000
        }
    
    while True:
        macro_context = load_macro_context()
        
        # Determine targets for this step interval (all symbols at once vs. one randomly selected symbol)
        targets = list(symbol_states.keys()) if sim_all_simultaneous else [random.choice(WATCHLIST)]
        
        for symbol in targets:
            state = symbol_states[symbol]
            state["step"] += 1
            step = state["step"]
            prev_price = state["price"]
            
            # Coordinated walk cycle to step assets through support levels & breakout triggers
            if 1 <= step <= 3:
                target_price = state["reversal_low"] + (state["reversal_high"] - state["reversal_low"]) / 2
                delta = (target_price - prev_price) / 2
                state["price"] += delta + random.uniform(-0.05, 0.05)
                volume = int(state["prev_vol"] * random.uniform(0.8, 1.2))
            elif step == 4:
                # Bounce support on extreme volume (Simulates Institutional Block Buying)
                state["price"] = (state["reversal_low"] + state["reversal_high"]) / 2
                volume = int(state["prev_vol"] * 3.0)  # RVOL = 3.0x (Sentry's 2.5x threshold breached!)
            elif 5 <= step <= 7:
                target_price = state["trigger"] - 0.20
                delta = (target_price - prev_price) / 2
                state["price"] += delta + random.uniform(-0.05, 0.05)
                volume = int(state["prev_vol"] * random.uniform(0.8, 1.2))
            elif step == 8:
                # Violent breakout above the tactical trigger line (Simulates Momentum Expansion)
                state["price"] = state["trigger"] + 0.35
                volume = int(state["prev_vol"] * 3.2)  # RVOL = 3.2x (Sentry's 2.5x threshold breached!)
            else:
                state["price"] = state["trigger"] - 1.5
                volume = 1000
                state["step"] = 0
            
            state["prev_vol"] = volume if volume > 0 else 1000
            
            bar_tick = {
                "symbol": symbol,
                "close": round(state["price"], 2),
                "volume": volume,
                "timestamp": datetime.now().isoformat()
            }
            
            print(f"BAR_TICK_DATA: {json.dumps(bar_tick)}", flush=True)
            
        time.sleep(sim_interval)

if __name__ == "__main__":
    # Resolve standard credential mappings
    api_key = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    api_secret = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
    
    if not api_key or not api_secret:
        log_msg("Alpaca API credentials not detected. Engaging standard Simulation fallback...")
        run_simulation_loop()
    else:
        log_msg("Active production credentials detected in environment.")
        try:
            asyncio.run(start_realtime_websocket_stream(api_key, api_secret))
        except KeyboardInterrupt:
            log_msg("Live streaming pipeline terminated cleanly by operator.")
        except Exception as e:
            log_msg(f"[!] Failed to launch streaming websocket: {e}. Falling back to simulation.")
            run_simulation_loop()
