import os
import sys
import sqlite3
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.getcwd())

print("=====================================================================")
print("🛰️  HARM.AI // AUTOMATED STATE LOCK & RE-ENTRY ASSERTION TEST")
print("=====================================================================")

# 1. Import LiveBot state (this triggers the new SQLite DB sync on load)
import src.LiveBot as LiveBot

def run_assertion():
    # 2. Check if PLTR was successfully pulled from SQLite into memory
    print(f"[*] Memory State: ACTIVE_TRADES = {LiveBot.ACTIVE_TRADES}")
    
    assert "PLTR" in LiveBot.ACTIVE_TRADES, "❌ FAIL: PLTR should be locked in ACTIVE_TRADES!"
    print("[✓] PASS: Active database position on PLTR successfully synced to memory.")

    # 3. Simulate an incoming price tick at a heavy support/breakout zone
    test_price = 129.00  # Right inside our VolumeProfiler adjusted targets
    print(f"[*] Simulating incoming market price for PLTR: ${test_price:.2f}")

    # 4. Fire the conviction matrix
    conviction = LiveBot.calculate_trade_conviction("PLTR", test_price, "LONG", 50000)
    print(f"[*] Conviction Engine Output: {conviction}")

    # 5. Assert that the re-entry is blocked
    assert conviction["action"] == "PASS", "❌ FAIL: Engine tried to execute a trade while active!"
    assert "Locked" in conviction["notes"], "❌ FAIL: Notes should indicate the trade is locked."
    
    print("-" * 69)
    print("[✓] ASSERTION PASSED: Double re-entry is physically blocked by State Lock!")
    print("[✓] Database and Execution Engine are perfectly integrated.")

if __name__ == "__main__":
    run_assertion()
