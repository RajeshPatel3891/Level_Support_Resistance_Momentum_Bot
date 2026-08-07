import time
import requests
import yfinance as yf
import pandas as pd

def send_discord_alert(ticker, action, price, detail=""):
    webhook_url = "https://discord.com/api/webhooks/1516048864325537847/fiH0REc5aHygxCfHFmplUA1tJlVfRJOI4MBRG4Oe0Kf_M2cigVyP5oPLgQvY9JG3vKk4"
    payload = {
        "embeds": [{
            "title": f"Harmonized AI Sentry: {action}",
            "color": 16711680 if "REJECTION" in action or "BOUNCE" in action else (3447003 if "GAP" in action else 16776960),
            "fields": [
                {"name": "Asset", "value": ticker, "inline": True},
                {"name": "Price", "value": f"${price:.2f}", "inline": True},
                {"name": "Detail", "value": detail, "inline": False}
            ]
        }]
    }
    requests.post(webhook_url, json=payload)

def adjust_for_gaps(ticker, day_open, static_levels):
    support = static_levels['support']
    resistance = static_levels['resistance']
    spread = resistance - support
    
    if day_open < support:
        new_sup = day_open - (spread * 0.5)
        new_res = day_open + (spread * 0.5)
        return {"support": new_sup, "resistance": new_res, "shifted": True, "dir": "DOWN"}
    elif day_open > resistance:
        new_sup = day_open - (spread * 0.5)
        new_res = day_open + (spread * 0.5)
        return {"support": new_sup, "resistance": new_res, "shifted": True, "dir": "UP"}
    
    return {"support": support, "resistance": resistance, "shifted": False, "dir": "NONE"}

def get_market_metrics(ticker):
    stock = yf.Ticker(ticker)
    df = stock.history(period="1d", interval="5m")
    if len(df) < 10: return None
    
    day_open = df['Open'].iloc[0]
    last_price = df['Close'].iloc[-1]
    
    # FIX: Only look at the last 6 candles (30 minutes) for interactions
    recent_window = df.tail(6)
    recent_high = recent_window['High'].max()
    recent_low = recent_window['Low'].min()
    
    sma50 = df['Close'].rolling(window=50).mean().iloc[-1] if len(df) >= 50 else df['Close'].mean()
    
    swing_high = df['High'].tail(20).max()
    swing_low = df['Low'].tail(20).min()
    fib_618 = swing_low + ((swing_high - swing_low) * 0.618)
    
    return {
        "open": day_open, "price": last_price, "recent_high": recent_high, "recent_low": recent_low, 
        "sma": sma50, "fib": fib_618
    }

def main():
    print("Harmonized AI Sentry v1.7 Online. [Mode: LOCALIZED ACTION & COOLDOWNS]")
    
    dpl_levels = {
        "SPY": {"support": 748.0, "resistance": 755.0},
        "QQQ": {"support": 733.50, "resistance": 743.0},
        "IWM": {"support": 296.66, "resistance": 300.0},
        "GOOGL": {"support": 350.0, "resistance": 380.0}
    }
    
    announced_shifts = []
    # FIX: Track the last fired alert per ticker to prevent spam
    last_alert = {t: {"type": None, "time": 0} for t in dpl_levels.keys()}
    
    while True:
        current_time = time.time()
        for ticker, levels in dpl_levels.items():
            data = get_market_metrics(ticker)
            if not data: continue
            
            active_levels = adjust_for_gaps(ticker, data['open'], levels)
            res = active_levels['resistance']
            sup = active_levels['support']
            
            shift_id = f"{ticker}_{data['open']}"
            if active_levels['shifted'] and shift_id not in announced_shifts:
                send_discord_alert(ticker, f"GAP_{active_levels['dir']}_ADJUSTMENT", data['open'], 
                                   f"Shifted DPL Zone: ${sup:.2f} -> ${res:.2f}")
                announced_shifts.append(shift_id)
            
            # 30-minute cooldown on identical alerts to prevent spam
            def can_alert(alert_type):
                if last_alert[ticker]["type"] == alert_type and (current_time - last_alert[ticker]["time"] < 1800):
                    return False
                return True
                
            def trigger_alert(alert_type, detail):
                if can_alert(alert_type):
                    send_discord_alert(ticker, alert_type, data['price'], detail)
                    last_alert[ticker] = {"type": alert_type, "time": current_time}

            # Proximity
            if abs(data['price'] - res) / res < 0.005:
                trigger_alert("PROXIMITY_RES", f"Near active resistance ${res:.2f}")
            elif abs(data['price'] - sup) / sup < 0.005:
                trigger_alert("PROXIMITY_SUP", f"Near active support ${sup:.2f}")
                
            # Confirmation (Using recent 30m window)
            if data['recent_high'] >= res and data['price'] < res:
                trigger_alert("REJECTION_CONFIRMED", "Resistance rejection confirmed.")
            elif data['recent_low'] <= sup and data['price'] > sup:
                trigger_alert("BOUNCE_CONFIRMED", "Support bounce confirmed.")
                
        time.sleep(300)

if __name__ == "__main__":
    main()
