import os, sys, json, requests, time
from datetime import datetime
from dotenv import load_dotenv

# 1. Load the Massive API key from the .env file immediately
load_dotenv()

from Connection import connect_massive_stream
from SignalBridge import read_signals, write_signals, init_bridge

# Load your manifest
MASTER_DATA = json.load(open('trading_levels.json', 'r'))
LEVEL_TIMER = {}
LIQUIDITY_HEARTBEAT = {}
COOLDOWN_TRACKER = {}  # Tracks last alert time per ticker

# RVOL Tracking Dictionaries
VOLUME_BUFFER = {}       # Stores tick volumes with timestamps
LOCAL_MINUTE_VOL = {}    # Stores the aggregated 60-second rolling volume

init_bridge()

def log_debug(message):
    with open("debug_trace.log", "a") as f:
        f.write(f"{datetime.now()} - {message}\n")

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
    
    log_debug(f"Calculated Dynamic Exits - Price: {p} | RVOL: {rvol:.2f} | Risk%: {dynamic_risk*100:.2f}% | SL: {sl:.2f} | TP1: {tp1:.2f}")
    return sl, tp1, tp2

def check_dark_pool_liquidity(ticker, price, conditions):
    is_liquid = conditions and any(c in [15, 38] for c in conditions)
    prev_was_liquid = LIQUIDITY_HEARTBEAT.get(ticker, False)
    LIQUIDITY_HEARTBEAT[ticker] = is_liquid
    if is_liquid:
        log_debug(f"Ticker: {ticker} | Liquidity Detected: {conditions} | Sequential: {prev_was_liquid}")
    return is_liquid and prev_was_liquid

def send_discord_alert(ticker, action, price, detail="", conviction_data=None):
    webhook_url = "https://discord.com/api/webhooks/1516048864325537847/fiH0REc5aHygxCfHFmplUA1tJlVfRJOI4MBRG4Oe0Kf_M2cigVyP5oPLgQvY9JG3vKk4"
    cso_notes = f"\n\n**[CSO CONVICTION MATRIX]**\n• **Conviction:** {conviction_data['conviction']} ({conviction_data['confidence']}% Confidence)\n• **Volume:** {conviction_data.get('volume_status', 'N/A')}\n• **Action:** {conviction_data['action']}\n• **Reasoning:** {conviction_data['notes']}" if conviction_data else ""
    
    # Only push structural shadow trades if it's a clean execution signal, not a cooldown violation
    if action == "EXECUTION" and conviction_data and conviction_data.get('conviction') == "HIGH":
        rvol = conviction_data.get('rvol', 1.0)
        sl, tp1, tp2 = calculate_exits(price, rvol)
        cso_notes += f"\n• **SL:** ${sl:.2f} | **TP1:** ${tp1:.2f} | **TP2:** ${tp2:.2f}"

        # --- SHADOW EXECUTION BRIDGE PUSH ---
        current_signals = read_signals()
        new_signal = {
            "id": f"{ticker}_{int(time.time())}",
            "timestamp": time.time(),
            "symbol": ticker,
            "entry_price": price,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "rvol": rvol,
            "status": "PENDING_BACKTEST"
        }
        current_signals.append(new_signal)
        write_signals(current_signals)

    payload = {
        "embeds": [{
            "title": f"Harmonized AI Sentry: {action}",
            "color": 16753920 if "VIOLATION" in action else (16711680 if "REJECTION" in action or "SHORT" in action else (65535 if "PROXIMITY" in action else (16776960 if "CAUTION" in action else 65280))),
            "fields": [
                {"name": "Asset", "value": ticker, "inline": True},
                {"name": "Price", "value": f"${price:.2f}", "inline": True},
                {"name": "Detail", "value": detail + cso_notes, "inline": False}
            ]
        }]
    }
    try: requests.post(webhook_url, json=payload)
    except Exception as e: print(f"DEBUG: Alert Error: {e}", file=sys.stderr)

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

def calculate_trade_conviction(ticker, current_price, trade_side, rolling_vol, conditions=None):
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
    
    dark_pool_signal = check_dark_pool_liquidity(ticker, price_f, conditions)
    support_window = 5.00 if dark_pool_signal else 2.50
    
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
            if dist <= support_window and dark_pool_signal:
                conf = int(90 * mod)
                return {"conviction": "HIGH", "confidence": conf, "action": "EXECUTE", "volume_status": "VALIDATED_LIQUIDITY", "rvol": rvol, "notes": "High-Conviction Sequential Dark Pool Scalp."}
            if dist <= 2.50 and vol_ok:
                conf = int(88 * mod)
                return {"conviction": "HIGH" if conf > 70 else "MEDIUM", "confidence": conf, "action": "EXECUTE", "volume_status": vol_status, "rvol": rvol, "notes": "Institutional Support Hold."}
            if dist <= 7.00:
                return {"conviction": "LOW", "confidence": int(40 * mod), "action": "PROXIMITY_SUP", "volume_status": vol_status, "rvol": rvol, "notes": "Proximity alert."}
    return {"conviction": "LOW", "confidence": 20, "action": "PASS", "volume_status": vol_status, "rvol": rvol, "notes": "Waiting for conviction or liquidity."}

def on_message(ws, message):
    try:
        events = json.loads(message)
        if not isinstance(events, list): events = [events]
        for e in events:
            if e.get("ev") == "T":
                tick_vol, sym, price = e.get("size", 0), e.get("sym"), e.get("price")
                conditions = e.get("conditions", e.get("c", []))
                
                if sym in MASTER_DATA["levels"]:
                    in_cooldown = (time.time() - COOLDOWN_TRACKER.get(sym, 0) < 300)
                    is_dark_pool = conditions and any(c in [15, 38] for c in conditions)
                    
                    if in_cooldown:
                        # Drop retail noise instantly
                        if not is_dark_pool:
                            continue
                        action_tag = "COOLDOWN_VIOLATION_DARK_POOL"
                    else:
                        action_tag = "EXECUTION"
                    
                    rolling_vol = update_rolling_volume(sym, tick_vol)
                    conv = calculate_trade_conviction(sym, price, "LONG", rolling_vol, conditions=conditions)
                    
                    if conv['action'] == "EXECUTE": 
                        # Reset cooldown tracking timestamp to keep the safety wrapper moving forward
                        COOLDOWN_TRACKER[sym] = time.time()
                        
                        detail_msg = "Signal triggered during active trading metrics." if action_tag == "EXECUTION" else "⚠️ ALERT: Heavy Dark Pool volume print detected inside active 300-second cooldown lock!"
                        send_discord_alert(sym, action_tag, price, detail_msg, conv)
                        
    except Exception as e: print(f"DEBUG: Message Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    print("Initializing Live Bot Stream Connection Engine...")
    connect_massive_stream(on_message)
