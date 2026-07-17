import sqlite3
import datetime
import os
import sys

# Ensure import paths are aligned
sys.path.append(os.getcwd())

from src.nvda_playbook import evaluate_call_entry, calculate_risk_parameters, TICKER_CALL

def force_entry():
    print("=====================================================================")
    print("🛸 HARM.AI // FORCE EXECUTION INJECTOR: NVDA")
    print("=====================================================================")
    
    # 1. Set pseudo spot price near your resistance level of ~214.0
    spot_price = 214.20
    print(f"[*] Simulating NVDA Spot Price: ${spot_price}")
    
    # 2. Trigger Playbook evaluation
    triggered, qty = evaluate_call_entry([], spot_price, spot_price)
    
    # 3. Get risk metrics
    risk = calculate_risk_parameters(spot_price, "CALL")
    
    # 4. Insert directly into the telemetry database
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    query = """
    INSERT INTO trades (
        ticker, timestamp, strategy, direction, support_level, 
        spot_price, stop_loss, take_profit, exit_status, net_pnl, is_live
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute(query, (
        "NVDA",
        timestamp,
        "BREAKOUT",
        "CALL",
        214.00,        # support_level
        spot_price,    # spot_price
        risk["stop_loss"],
        risk["tp1"],
        "ACTIVE",      # exit_status
        0.0,           # net_pnl
        0              # is_live (0 for paper/sim)
    ))
    
    conn.commit()
    conn.close()
    print(f"[✓] Complete. Forced NVDA trade logged to harm_telemetry.db @ {spot_price}")

if __name__ == "__main__":
    force_entry()
