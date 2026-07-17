import sqlite3
import datetime
import os
import sys

# Ensure import paths are aligned
sys.path.append(os.getcwd())

from src.pltr_playbook import evaluate_call_entry, calculate_risk_parameters, TICKER_CALL

def force_entry():
    print("=====================================================================")
    print("🛸 HARM.AI // FORCE EXECUTION INJECTOR ACTIVE")
    print("=====================================================================")
    
    # 1. Grab current pseudo spot price for PLTR
    spot_price = 131.02
    print(f"[*] Simulating PLTR Spot Price: ${spot_price}")
    
    # 2. Trigger Playbook evaluation
    triggered, qty = evaluate_call_entry([], spot_price, spot_price)
    if not triggered:
        print("[-] Playbook refused to trigger.")
        return
        
    print(f"[🔥 TRIGGER] PLTR Bullish Support confirmed. Sizing: {qty} contracts.")
    
    # 3. Get risk metrics
    risk = calculate_risk_parameters(spot_price, "CALL")
    
    # 4. Insert directly into the telemetry database
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    # We match your database table columns exactly
    query = """
    INSERT INTO trades (
        ticker, timestamp, strategy, direction, support_level, 
        spot_price, stop_loss, take_profit, exit_status, net_pnl, is_live
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute(query, (
        "PLTR",
        timestamp,
        "BREAKOUT",
        "CALL",
        130.50,         # support_level
        spot_price,     # spot_price
        risk["stop_loss"],
        risk["tp1"],
        "ACTIVE",       # exit_status
        0.0,            # net_pnl
        0               # is_live (0 for paper/sim)
    ))
    
    conn.commit()
    conn.close()
    print("[✓] Complete. Forced trade logged successfully to harm_telemetry.db!")

if __name__ == "__main__":
    force_entry()
