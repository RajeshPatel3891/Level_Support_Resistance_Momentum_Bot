import os, sys, json, websocket, requests
from datetime import datetime
from Connection import connect_massive_stream

# Load your manifest
MASTER_DATA = json.load(open('trading_levels.json', 'r'))

def send_discord_alert(ticker, action, price, detail="", conviction_data=None):
    webhook_url = "https://discord.com/api/webhooks/1516048864325537847/fiH0REc5aHygxCfHFmplUA1tJlVfRJOI4MBRG4Oe0Kf_M2cigVyP5oPLgQvY9JG3vKk4"
    cso_notes = f"\n\n**[CSO CONVICTION MATRIX]**\n• **Conviction:** {conviction_data['conviction']} ({conviction_data['confidence']}% Confidence)\n• **Volume:** {conviction_data.get('volume_status', 'N/A')}\n• **Action:** {conviction_data['action']}\n• **Reasoning:** {conviction_data['notes']}" if conviction_data else ""
    payload = {
        "embeds": [{
            "title": f"Harmonized AI Sentry: {action}",
            "color": 16711680 if "REJECTION" in action or "SHORT" in action else (65535 if "PROXIMITY" in action else 65280),
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

def calculate_trade_conviction(ticker, current_price, trade_side, curr_vol):
    if is_opening_range() and trade_side == "LONG":
        return {"conviction": "LOW", "confidence": 10, "action": "PASS", "notes": "Volatility Damper: Opening Range."}
    
    asset = MASTER_DATA["levels"].get(ticker)
    if not asset: return {"conviction": "NONE", "confidence": 0, "action": "PASS", "notes": "No manifest."}
    
    macro, tactical = asset.get("algo_macro", {}), asset.get("human_tactical", {})
    avg_vol = asset.get("avg_volume", 1000)
    vol_ok = curr_vol > (avg_vol * 1.2)
    print(f"DEBUG_LOGIC: Vol: {curr_vol}, Target: {avg_vol * 1.2}, OK: {vol_ok}", file=sys.stderr)
    vol_status = f"{curr_vol/avg_vol:.1f}x Avg Volume"
    
    if trade_side == "SHORT":
        breakdown_trig = tactical.get("breakdown_trigger")
        if breakdown_trig and current_price < breakdown_trig and vol_ok:
            return {"conviction": "HIGH", "confidence": 95, "action": "EXECUTE", "volume_status": vol_status, "notes": "Strong volume breakdown."}
    elif trade_side == "LONG":
        support = macro.get("support", [0])[0]
        # Execution Zone
        if support and abs(current_price - support) <= 0.75 and vol_ok:
            return {"conviction": "HIGH", "confidence": 88, "action": "EXECUTE", "volume_status": vol_status, "notes": "Strong volume support hold."}
        # Proximity Zone
        if support and 0.75 < (current_price - support) <= 2.00:
            return {"conviction": "LOW", "confidence": 50, "action": "PROXIMITY_SUP", "volume_status": vol_status, "notes": f"Proximity alert: Approaching support at ${support:.2f}"}
             
    print("DEBUG_LOGIC: Conviction triggered: LOW (No trigger met)", file=sys.stderr)
    return {"conviction": "LOW", "confidence": 20, "action": "PASS", "volume_status": vol_status, "notes": "Insufficient volume or churn."}

def on_message(ws, message):
    try:
        events = json.loads(message)
        if not isinstance(events, list): events = [events]
        for e in events:
            if e.get("ev") == "status" and e.get("status") == "auth_success":
                print("Sentry: Authenticated successfully!", file=sys.stderr)
                symbols = ",".join([f"AM.{sym}" for sym in MASTER_DATA["levels"].keys()])
                ws.send(json.dumps({"action": "subscribe", "params": symbols}))
            elif e.get("ev") == "T":
                vol, sym, price = e.get("v", 0), e.get("sym"), e.get("p")
                asset = MASTER_DATA["levels"].get(sym)
                if not asset: continue
                
                # Check Execute/Proximity Logic
                if vol > (asset.get("avg_volume", 1000) * 1.9):
                    macro = asset.get("algo_macro", {})
                    res, sup = macro.get("resistance", [9999])[0], macro.get("support", [0])[0]
                    
                    if price >= res:
                        conv = calculate_trade_conviction(sym, price, "SHORT", vol)
                        if conv['action'] == "EXECUTE":
                            send_discord_alert(sym, "REJECTION_CONFIRMED", price, "Resistance rejection.", conv)
                    elif price <= (sup + 2.00): # Trigger if within 2.00 of support
                        conv = calculate_trade_conviction(sym, price, "LONG", vol)
                        if conv['action'] == "EXECUTE":
                            send_discord_alert(sym, "BOUNCE_CONFIRMED", price, "Support bounce.", conv)
                        elif conv['action'] == "PROXIMITY_SUP":
                            send_discord_alert(sym, "PROXIMITY_SUP", price, f"Approaching floor band ${sup:.2f}", conv)
    except Exception as e:
        print(f"DEBUG: Message Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    connect_massive_stream(on_message)
