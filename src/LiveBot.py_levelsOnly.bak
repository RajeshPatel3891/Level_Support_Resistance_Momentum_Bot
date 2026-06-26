import time
import json
import requests
import yfinance as yf
import pandas as pd
from datetime import datetime

def send_discord_alert(ticker, action, price, detail="", conviction_data=None):
    webhook_url = "https://discord.com/api/webhooks/1516048864325537847/fiH0REc5aHygxCfHFmplUA1tJlVfRJOI4MBRG4Oe0Kf_M2cigVyP5oPLgQvY9JG3vKk4"
    cso_notes = f"\n\n**[CSO CONVICTION MATRIX]**\n• **Conviction:** {conviction_data['conviction']} ({conviction_data['confidence']}% Confidence)\n• **Volume:** {conviction_data.get('volume_status', 'N/A')}\n• **Action:** {conviction_data['action']}\n• **Reasoning:** {conviction_data['notes']}" if conviction_data else ""
    payload = {
        "embeds": [{
            "title": f"Harmonized AI Sentry: {action}",
            "color": 16711680 if "REJECTION" in action or "SHORT" in action else 65280,
            "fields": [
                {"name": "Asset", "value": ticker, "inline": True},
                {"name": "Price", "value": f"${price:.2f}", "inline": True},
                {"name": "Detail", "value": detail + cso_notes, "inline": False}
            ]
        }]
    }
    requests.post(webhook_url, json=payload)

def is_opening_range():
    now = datetime.now()
    return now.hour == 9 and 30 <= now.minute < 45

def load_integrated_levels():
    try:
        with open("trading_levels.json", "r") as f:
            return json.load(f)
    except Exception: return None

def check_volume_confirmation(df):
    """Requires current volume > 1.2x of the 20-period moving average."""
    avg_vol = df['Volume'].rolling(window=20).mean().iloc[-1]
    curr_vol = df['Volume'].iloc[-1]
    return curr_vol > (avg_vol * 1.2), f"{curr_vol/avg_vol:.1f}x Avg Volume"

def calculate_trade_conviction(ticker, current_price, trade_side, master_data, df):
    if is_opening_range() and trade_side == "LONG":
        return {"conviction": "LOW", "confidence": 10, "action": "PASS", "volume_status": "N/A", "notes": "Volatility Damper: Opening Range."}

    vol_ok, vol_status = check_volume_confirmation(df)
    
    asset = master_data["levels"].get(ticker)
    if not asset: return {"conviction": "NONE", "confidence": 0, "action": "PASS", "volume_status": vol_status, "notes": "No manifest."}
    
    macro = asset.get("algo_macro", {})
    tactical = asset.get("human_tactical", {})
    
    if trade_side == "SHORT":
        breakdown_trig = tactical.get("breakdown_trigger")
        if breakdown_trig and current_price < breakdown_trig and vol_ok:
            return {"conviction": "HIGH", "confidence": 95, "action": "EXECUTE", "volume_status": vol_status, "notes": "Strong volume breakdown."}
    elif trade_side == "LONG":
        support = macro.get("support", [0])[0]
        if support and abs(current_price - support) <= 0.75 and vol_ok:
            return {"conviction": "HIGH", "confidence": 88, "action": "EXECUTE", "volume_status": vol_status, "notes": "Strong volume support hold."}
            
    return {"conviction": "LOW", "confidence": 20, "action": "PASS", "volume_status": vol_status, "notes": "Insufficient volume or churn."}

def get_market_metrics(ticker):
    stock = yf.Ticker(ticker)
    try:
        df = stock.history(period="5d", interval="5m")
        if len(df) < 20: return None
        return {"price": stock.fast_info['last_price'], "recent_high": df.tail(6)['High'].max(), "recent_low": df.tail(6)['Low'].min(), "df": df}
    except Exception: return None

def main():
    print("Harmonized AI Sentry v1.7.6 Online. [Mode: VOLUME_CONFIRMED]")
    last_alert = {}
    while True:
        master_data = load_integrated_levels()
        if master_data:
            for ticker, asset_data in master_data["levels"].items():
                data = get_market_metrics(ticker)
                if not data: continue
                macro = asset_data.get("algo_macro", {})
                res, sup = macro.get("resistance", [9999])[0], macro.get("support", [0])[0]
                
                def trigger(alert_type, side, msg):
                    conv = calculate_trade_conviction(ticker, data['price'], side, master_data, data['df'])
                    send_discord_alert(ticker, alert_type, data['price'], msg, conv)
                
                if data['recent_high'] >= res and data['price'] < res:
                    trigger("REJECTION_CONFIRMED", "SHORT", "Resistance rejection.")
                elif data['recent_low'] <= sup and data['price'] > sup:
                    trigger("BOUNCE_CONFIRMED", "LONG", "Support bounce.")
        time.sleep(30)

if __name__ == "__main__":
    main()
