import sys
import sqlite3
import json
from src.forced_entry_guard import can_tactical_force_entry

def force_entry(ticker, direction):
    spot_price = 205.65 if ticker == "NVDA" else (310.19 if ticker == "TSLA" else 100.0)
    
    live_quote = {
        "bid": 2.10,
        "ask": 2.15,
        "last": spot_price,
        "high": spot_price + 0.25,
        "low": spot_price - 0.25
    }
    atr_val = 0.45

    print(f"\n[🔄 EVALUATING FORCED ENTRY] Ticker: {ticker} | Direction: {direction}")
    
    allowed, message = can_tactical_force_entry(ticker, direction, live_quote, atr_val)
    print(f"[🛡️ TACTICAL GUARD] {message}")
    
    if not allowed:
        print("[X] Force entry cancelled to protect capital.\n")
        return False

    print(f"[🚀 EXECUTE] Guard passed! Injecting forced trade for {ticker}...")
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    # Store spot_price in entry_price so dashboard PnL delta calculation remains 1:1
    cursor.execute("""
        INSERT INTO trades (ticker, spot_price, stop_loss, take_profit, timestamp, entry_price, shares, direction, exit_status, strategy)
        VALUES (?, ?, ?, ?, DATETIME('now'), ?, 1.0, ?, 'ACTIVE', 'TACTICAL_FORCE')
    """, (ticker, live_quote['last'], live_quote['last'] * 0.98, live_quote['last'] * 1.05, live_quote['last'], direction))
    
    conn.commit()
    conn.close()
    print(f"[✓] Position {ticker} ({direction}) successfully injected!\n")
    return True

if __name__ == "__main__":
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else "NVDA"
    direction = sys.argv[2].upper() if len(sys.argv) > 2 else "CALL"
    force_entry(ticker, direction)
