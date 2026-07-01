import os
import sys
import json
import time
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from alpaca.data.live import StockDataStream

# 1. Load context environments
load_dotenv()
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

from SignalBridge import read_signals, write_signals, init_bridge
from AlertManager import send_discord_alert

# 2. State & Manifest Configuration
MASTER_DATA = json.load(open('trading_levels.json', 'r'))
LEVEL_TIMER = {}
COOLDOWN_TRACKER = {}

# RVOL Tracking Matrices
VOLUME_BUFFER = {}
LOCAL_MINUTE_VOL = {}

init_bridge()

def update_rolling_volume(ticker, tick_vol):
    """Aggregates tick volume into a 60-second rolling window."""
    now = time.time()
    if ticker not in VOLUME_BUFFER:
        VOLUME_BUFFER[ticker] = []
    
    VOLUME_BUFFER[ticker].append((now, tick_vol))
    VOLUME_BUFFER[ticker] = [v for v in VOLUME_BUFFER[ticker] if now - v[0] <= 60]
    LOCAL_MINUTE_VOL[ticker] = sum(v[1] for v in VOLUME_BUFFER[ticker])
    return LOCAL_MINUTE_VOL[ticker]

def calculate_exits(entry_price, rvol):
    """Dynamically calculates exits based on relative volume velocity."""
    p = float(entry_price)
    base_risk_pct = 0.005 
    volatility_multiplier = max(0.5, min(1.5, rvol)) 
    dynamic_risk = base_risk_pct * volatility_multiplier
    risk_dollars = p * dynamic_risk
    
    sl = p - risk_dollars
    tp1 = p + (risk_dollars * 2) 
    tp2 = p + (risk_dollars * 4) 
    return sl, tp1, tp2

def is_opening_range():
    now = datetime.now()
    return now.hour == 9 and 30 <= now.minute < 45

def check_for_reversal(ticker, rolling_vol):
    asset = MASTER_DATA["levels"].get(ticker)
    return rolling_vol > (asset.get("avg_volume", 1000) * 2.5) if asset else False

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

def calculate_trade_conviction(ticker, current_price, trade_side, rolling_vol):
    if current_price is None:
        return {"conviction": "NONE", "confidence": 0, "action": "PASS", "notes": "Invalid price data."}
    if is_opening_range() and trade_side == "LONG":
        return {"conviction": "LOW", "confidence": 10, "action": "PASS", "notes": "Volatility Damper: Opening Range."}
    
    asset = MASTER_DATA["levels"].get(ticker)
    if not asset: return {"conviction": "NONE", "confidence": 0, "action": "PASS", "notes": "No manifest."}
    
    macro, tactical = asset.get("algo_macro", {}), asset.get("human_tactical", {})
    avg_vol = asset.get("avg_volume", 1000)
    LEVEL_TIMER[ticker] = LEVEL_TIMER.get(ticker, 0) + 1
    
    rvol = rolling_vol / avg_vol if avg_vol > 0 else 0
    vol_status = f"{rvol:.2f}x Avg Volume (RVOL)"
    
    vol_ok = rvol > 0.8
    if LEVEL_TIMER[ticker] > 10: vol_ok = rvol > 0.5
    
    price_f = float(current_price)
    mod = get_tactical_modifier(ticker, price_f, trade_side)
    
    if check_for_reversal(ticker, rolling_vol):
        return {"conviction": "MEDIUM", "confidence": 60, "action": "CAUTION", "volume_status": vol_status, "rvol": rvol, "notes": "Reversal Momentum Detected: Institutional absorption."}
    
    if trade_side == "SHORT":
        breakdown_trig = tactical.get("breakdown_trigger")
        if breakdown_trig and price_f < float(breakdown_trig) and vol_ok:
            conf = int(95 * mod)
            return {"conviction": "HIGH" if conf > 70 else "MEDIUM", "confidence": conf, "action": "EXECUTE", "volume_status": vol_status, "rvol": rvol, "notes": "Strong volume breakdown."}
    elif trade_side == "LONG":
        support = macro.get("support", [None])[0]
        if support is not None:
            support_f = float(support)
            dist = abs(price_f - support_f)
            if dist <= 2.50 and vol_ok:
                conf = int(88 * mod)
                return {"conviction": "HIGH" if conf > 70 else "MEDIUM", "confidence": conf, "action": "EXECUTE", "volume_status": vol_status, "rvol": rvol, "notes": "Institutional Support Hold."}
            if dist <= 7.00:
                return {"conviction": "LOW", "confidence": int(40 * mod), "action": "PROXIMITY_SUP", "volume_status": vol_status, "rvol": rvol, "notes": "Proximity alert."}
    return {"conviction": "LOW", "confidence": 20, "action": "PASS", "volume_status": vol_status, "rvol": rvol, "notes": "Waiting for conviction."}

# 3. Dynamic Signal Pipeline Hook
def process_incoming_tick(symbol, price, volume):
    if symbol not in MASTER_DATA["levels"]:
        return

    in_cooldown = (time.time() - COOLDOWN_TRACKER.get(symbol, 0) < 300)
    if in_cooldown:
        return # Drop noise during cooldown locks

    rolling_vol = update_rolling_volume(symbol, volume)
    
    # Evaluate Strategy Matrix
    conv = calculate_trade_conviction(symbol, price, "LONG", rolling_vol)
    
    if conv['action'] == "EXECUTE":
        COOLDOWN_TRACKER[symbol] = time.time()
        
        # Calculate Exits and Construct the complete CSO Conviction Matrix details
        rvol = conv.get('rvol', 1.0)
        sl, tp1, tp2 = calculate_exits(price, rvol)
        
        cso_notes = f"Signal triggered during active trading metrics.\n\n"
        cso_notes += f"**[CSO CONVICTION MATRIX]**\n"
        cso_notes += f"• **Conviction:** {conv['conviction']} ({conv['confidence']}% Confidence)\n"
        cso_notes += f"• **Volume:** {conv.get('volume_status', 'N/A')}\n"
        cso_notes += f"• **Action:** {conv['action']}\n"
        cso_notes += f"• **Reasoning:** {conv['notes']}\n"
        cso_notes += f"• **SL:** ${sl:.2f} | **TP1:** ${tp1:.2f} | **TP2:** ${tp2:.2f}"
        
        # --- SHADOW EXECUTION BRIDGE PUSH ---
        current_signals = read_signals()
        new_signal = {
            "id": f"{symbol}_{int(time.time())}",
            "timestamp": time.time(),
            "symbol": symbol,
            "ticker": symbol,
            "entry_price": price,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "rvol": rvol,
            "status": "PENDING_BACKTEST"
        }
        current_signals.append(new_signal)
        write_signals(current_signals)
        
        print(f">>> Strategy Matrix Match! Triggering Signal Bridge Entry for {symbol} at ${price:.2f}")
        send_discord_alert(symbol, "EXECUTION", price, cso_notes, conv)

async def main():
    print("[*] Initializing Alpaca Real-Time Live Stream Protocol...")
    if not API_KEY or not SECRET_KEY:
        print("[!] Execution Halted: Missing credentials in env.")
        return

    stream_client = StockDataStream(API_KEY, SECRET_KEY)
    
    async def handle_realtime_trade(data):
        process_incoming_tick(data.symbol, data.price, data.size)

    active_symbols = list(MASTER_DATA["levels"].keys())
    print(f"[*] Extracted active watchlist targets: {active_symbols}")
    
    for symbol in active_symbols:
        stream_client.subscribe_trades(handle_realtime_trade, symbol)
        
    print("[*] Active pipeline subscriptions verified. Opening live socket...")
    await stream_client._run_forever()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Alpaca Stream terminated cleanly by developer request.")
