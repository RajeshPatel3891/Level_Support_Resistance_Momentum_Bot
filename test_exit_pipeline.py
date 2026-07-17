import os
import sys
import json
import sqlite3
from dotenv import load_dotenv

load_dotenv()
sys.path.append(os.getcwd())

print("=====================================================================")
print("🛰️  HARM.AI // AUTOMATED REAL-TIME EXIT PIPELINE INTEGRATION TEST")
print("=====================================================================")

import src.LiveBot as LiveBot

def run_exit_test():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, spot_price, stop_loss, take_profit, exit_status FROM trades WHERE id = 22;")
    trade = cursor.fetchone()
    conn.close()

    if not trade:
        print("❌ FAIL: Active trade with ID 22 not found in database.")
        return

    trade_id, entry, stop_loss, take_profit, status = trade
    print(f"[*] Target Position Sync\x27d from DB (ID: {trade_id}):")
    print(f"    • Entry Price: ${entry:.2f}")
    print(f"    • Stop Loss:   ${stop_loss:.2f}")
    print(f"    • Take Profit: ${take_profit:.2f}")
    print(f"    • Current DB Status: {status}")
    print("-" * 69)

    LiveBot.ACTIVE_TRADES["PLTR"] = True

    # --- SIMULATION BLOCK 1: Safe Pricing Tick ---
    safe_price = 131.00
    print(f"[*] SIMULATION 1: Sending safe trade tick for PLTR @ ${safe_price:.2f}")
    mock_payload_safe = json.dumps([{"ev": "T", "sym": "PLTR", "price": safe_price, "size": 1500}])
    LiveBot.on_message(None, mock_payload_safe)
    
    assert LiveBot.ACTIVE_TRADES.get("PLTR") is True, "❌ FAIL: Bot exited early!"
    print("[✓] PASS: Position remained stable.")
    print("-" * 69)

    # --- SIMULATION BLOCK 2: Take Profit Breach Tick ---
    target_price = 136.00
    print(f"[*] SIMULATION 2: Sending breakout tick for PLTR @ ${target_price:.2f} (Breaching TP of ${take_profit:.2f})")
    mock_payload_breach = json.dumps([{"ev": "T", "sym": "PLTR", "price": target_price, "size": 3000}])
    LiveBot.on_message(None, mock_payload_breach)

    # --- ASSERTION CHECK ---
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    cursor.execute("SELECT exit_status, net_pnl FROM trades WHERE id = 22;")
    updated_trade = cursor.fetchone()
    conn.close()

    print("-" * 69)
    print(f"[*] Post-Execution Memory Lock: ACTIVE_TRADES[\x27PLTR\x27] = {LiveBot.ACTIVE_TRADES.get("PLTR")}")
    print(f"[*] Post-Execution DB Status: {updated_trade[0]} | net_pnl = {updated_trade[1]}")

    assert LiveBot.ACTIVE_TRADES.get("PLTR") is False, "❌ FAIL: Memory lock did not release!"
    assert updated_trade[0] == "TAKE_PROFIT", "❌ FAIL: DB state did not update!"
    
    print("=====================================================================")
    print("[✓] INTEGRATION SUCCESS: Exit successfully simulated and verified!")
    print("=====================================================================")

if __name__ == "__main__":
    run_exit_test()
