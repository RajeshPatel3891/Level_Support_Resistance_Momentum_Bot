import json
import os
import urllib.request
import sys

# Reconciled Environment Injection Layer with Master Path Fallback
ENV_WEBHOOK = os.getenv("DISCORD_URL", "")
STATIC_WEBHOOK = "https://discord.com/api/webhooks/1516048864325537847/fiH0REc5aHygxCfHFmplUA1tJlVfRJOI4MBRG4Oe0Kf_M2cigVyP5oPLgQvY9JG3vKk4"
DISCORD_WEBHOOK_URL = ENV_WEBHOOK if ENV_WEBHOOK else STATIC_WEBHOOK

def load_market_data():
    filepath = "todays_market_history.json"
    if not os.path.exists(filepath):
        print(f"[!] Target data layer '{filepath}' missing. Mocking sample row distribution for test execution.")
        return {
            "SPY": [
                {"time": "09:31:00", "close": 747.50, "volume": 12000},
                {"time": "09:32:00", "close": 748.50, "volume": 45000}, # The Impulse Wave
                {"time": "09:33:00", "close": 748.12, "volume": 15000}, # 38.2% Pullback Entry
                {"time": "09:34:00", "close": 748.80, "volume": 22000}  # Hit Extension Target
            ]
        }
    with open(filepath, 'r') as f:
        return json.load(f)

def broadcast_to_discord(symbol, wave_range, entry_limit, target_tp, cash_yield):
    """
    Formattings match your master branch discord requirements.
    Pushes immediate, high-scannability markdown blocks to the analyst channel.
    """
    if not DISCORD_WEBHOOK_URL or "YOUR_WEBHOOK_ID" in DISCORD_WEBHOOK_URL:
        print(f"      [!] Skipping broadcast for {symbol} (No live environment Webhook URL configured).")
        return 
        
    payload = {
        "embeds": [{
            "title": f"⚡ HARM.AI SIDEKICK // LIVE MICRO-SCALPING SIMULATION",
            "color": 1100150, # Emerald Green Hex Map equivalent
            "description": (
                f"**Asset Target:** `{symbol}`\n"
                f"**Impulse Vector Range:** `${wave_range:.2f}`\n\n"
                f"```ini\n"
                f"[SIMULATED BRACKET PARAMETERS]\n"
                f"• Position Size       : 5 Contracts (0DTE)\n"
                f"• Calculated Entry Limit : ${entry_limit:.2f}\n"
                f"• Target Profit (OCO)   : ${target_tp:.2f}\n"
                f"• Stop Loss Limit (30%) : Premium -30%\n"
                f"```\n"
                f"**Simulated Cash Scrape:** `+${cash_yield:.2f}` 🎉"
            ),
            "footer": {"text": "Backtest Replay Frame // 2026 Hist-Data Stream Locked"}
        }]
    }
    
    try:
        req = urllib.request.Request(
            DISCORD_WEBHOOK_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={'User-Agent': 'HarmonizedSentryBot/1.1', 'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req) as response:
            if response.status in [200, 204]:
                print(f"      [✓] Discord alert cleanly delivered for {symbol}!")
    except Exception as e:
        print(f"      [!] Webhook transmission failure for {symbol}: {str(e)}")

def run_simulation():
    data = load_market_data()
    print("======================================================================")
    print("      LAUNCHING 0DTE HIGH-FREQUENCY MICRO-SCALP BACKTEST ENGINE")
    print("      Configuration: 5 Contracts | Range Guard: $0.20 | Delta: 0.50")
    print("======================================================================\n")
    
    for symbol, candles in data.items():
        if len(candles) < 3: continue
        print(f"[*] Scanning data arrays for target instrument: {symbol}")
        
        # Iterates over window intervals to locate local volume surges
        for i in range(1, len(candles) - 1):
            prev_v = candles[i-1]["volume"]
            curr_v = candles[i]["volume"]
            
            # Simple RVOL proxy filter check
            if prev_v > 0 and (curr_v / prev_v) >= 2.5:
                swing_low = candles[i-1]["close"]
                swing_high = candles[i]["close"]
                wave_distance = swing_high - swing_low
                
                if wave_distance <= 0: continue
                if wave_distance < 0.20: continue # Range Hardening Guardrail Active
                
                # Math formulas matching your proposed blueprint
                fib_entry_stock = swing_high - (0.382 * wave_distance)
                fib_target_stock = swing_high + (0.272 * wave_distance)
                
                # Check subsequent candles to verify fulfillment loops
                for j in range(i+1, min(i+5, len(candles))):
                    future_close = candles[j]["close"]
                    if future_close <= fib_entry_stock:
                        stock_move_required = fib_target_stock - fib_entry_stock
                        options_premium_gain = stock_move_required * 0.50 # Delta scale factor
                        gross_cash_scrape = 5 * (options_premium_gain * 100)
                        
                        print(f"  [+] Triggered {symbol} -> Broadcasting to Sidekick Channel...")
                        broadcast_to_discord(
                            symbol=symbol,
                            wave_range=wave_distance,
                            entry_limit=fib_entry_stock,
                            target_tp=fib_target_stock,
                            cash_yield=gross_cash_scrape
                        )
                        break
                break

if __name__ == "__main__":
    run_simulation()
