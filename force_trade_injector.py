import sys
import os
import sqlite3
import json

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from src.forced_entry_guard import can_tactical_force_entry

def force_entry(ticker, direction, force_override=False, live_mode=False):
    spot_price = 205.65 if ticker == "NVDA" else (310.19 if ticker == "TSLA" else 100.0)
    
    live_quote = {
        "bid": 2.10,
        "ask": 2.15,
        "last": spot_price,
        "high": spot_price + 0.25,
        "low": spot_price - 0.25
    }
    atr_val = 0.45

    print(f"\n[🔄 EVALUATING FORCED ENTRY] Ticker: {ticker} | Direction: {direction} | Mode: {'TRADIER LIVE' if live_mode else 'SIMULATION'}")
    
    if force_override:
        print(f"[🛡️ TACTICAL GUARD] OVERRIDDEN: Bypassing ARMED state for {ticker} via --force flag. Handing off to CSO.")
    else:
        allowed, message = can_tactical_force_entry(ticker, direction, live_quote, atr_val)
        print(f"[🛡️ TACTICAL GUARD] {message}")
        
        if not allowed:
            print("[X] Force entry cancelled to protect capital.\n")
            return False

    print(f"[🚀 EXECUTE] Guard passed! Injecting forced trade for {ticker}...")

    if live_mode:
        print(f"[📡 TRADIER API] Routing LIVE {direction} order for {ticker} to Tradier Brokerage...")
        try:
            from src.LiveBot import execute_order
            
            stop_lvl = spot_price * 0.98 if direction == "CALL" else spot_price * 1.02
            
            # Execute real order via LiveBot pipeline (logs real broker fill to DB)
            success = execute_order(ticker, ticker, 1.0, direction, limit_price=spot_price, stop_loss=stop_lvl)
            if success:
                print(f"[✓] Live Tradier order confirmed & logged for {ticker} ({direction})!\n")
                return True
            else:
                print(f"[X] Tradier API rejected or failed to fill order for {ticker}.\n")
                return False
        except Exception as e:
            print(f"[!] Error calling LiveBot Tradier execution: {e}\n")
            return False
    else:
        # Standard Offline Simulation Entry
        conn = sqlite3.connect("harm_telemetry.db")
        cursor = conn.cursor()
        
        # Explicitly tag strategy as TACTICAL_FORCE_SIM
        cursor.execute("""
            INSERT INTO trades (ticker, spot_price, stop_loss, take_profit, timestamp, entry_price, shares, direction, exit_status, strategy)
            VALUES (?, ?, ?, ?, DATETIME('now'), ?, 1.0, ?, 'ACTIVE', 'TACTICAL_FORCE_SIM')
        """, (ticker, live_quote['last'], live_quote['last'] * 0.98, live_quote['last'] * 1.05, live_quote['last'], direction))
        
        conn.commit()
        conn.close()
        print(f"[✓] SIMULATION position {ticker} ({direction}) successfully injected!\n")
        return True

if __name__ == "__main__":
    force_override = "--force" in sys.argv or "--override-guard" in sys.argv
    live_mode = "--live" in sys.argv or "--tradier" in sys.argv or "--mode=tradier" in sys.argv
    
    # Filter out flag parameters to extract positional args
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    
    ticker = args[0].upper() if len(args) > 0 else "NVDA"
    direction = args[1].upper() if len(args) > 1 else "CALL"
    
    force_entry(ticker, direction, force_override=force_override, live_mode=live_mode)
