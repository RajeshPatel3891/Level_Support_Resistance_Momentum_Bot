import json
from datetime import datetime

def run_tape_audit():
    print("[*] Initializing Historical Tape Audit Engine...")

    # 1. Load today's historical market bars
    try:
        with open("todays_market_history.json", "r") as f:
            market_data = json.load(f)
    except Exception as e:
        print(f"[!] Failed to load market history: {e}")
        return

    # 2. Hardcode the exact execution signals captured by your bot logs
    executed_trades = [
        {"symbol": "IWM", "entry_price": 300.61, "timestamp": "2026-07-01T14:15:00", "risk_dollars": 2.25},
        {"symbol": "NVDA", "entry_price": 194.51, "timestamp": "2026-07-01T15:02:00", "risk_dollars": 1.46},
        {"symbol": "SPY", "entry_price": 743.02, "timestamp": "2026-07-01T13:45:00", "risk_dollars": 5.57}
    ]

    total_sim_pl = 0.0

    print("\n========================================================")
    print("           TODAY'S TAPELOG EXECUTION AUDIT             ")
    print("========================================================\n")

    for trade in executed_trades:
        sym = trade["symbol"]
        entry = trade["entry_price"]
        r = trade["risk_dollars"]
        
        # Calculate strict algorithmic exits
        sl_target = entry - r
        tp1_target = entry + (r * 2)
        
        bars = market_data.get(sym, [])
        trade_triggered = False
        outcome = "OPEN / RUNNING"
        exit_price = entry
        
        # Filter bars to only look *after* the execution timestamp
        for bar in bars:
            bar_time = bar["time"]
            if bar_time < trade["timestamp"]:
                continue
                
            high_p = bar["high"]
            low_p = bar["low"]
            
            # Check if Stop Loss was penetrated first
            if low_p <= sl_target:
                outcome = "STOP LOSS HIT (LOSS)"
                exit_price = sl_target
                trade_triggered = True
                break
                
            # Check if Take Profit 1 was penetrated first
            if high_p >= tp1_target:
                outcome = "TAKE PROFIT 1 HIT (WIN)"
                exit_price = tp1_target
                trade_triggered = True
                break

        # Calculate P&L based on 2 contracts moving at a 0.50 Delta ($1.00 move = $100 total for 2 contracts)
        price_diff = exit_price - entry
        trade_pl = price_diff * 100.0
        total_sim_pl += trade_pl
        
        print(f"• ASSET: {sym}")
        print(f"  Entry Price: ${entry:.2f} | Timestamp: {trade['timestamp']}")
        print(f"  Calculated Exit Windows -> SL: ${sl_target:.2f} | TP1: ${tp1_target:.2f}")
        print(f"  Realized Session Outcome: {outcome}")
        print(f"  Trade Net P&L (2 Contracts @ 0.50 Delta): {'+$' if trade_pl >= 0 else '-$'}{abs(trade_pl):.2f}\n")

    print("========================================================")
    print(f"TOTAL REALIZED SESSION P&L MATRICES: {'+$' if total_sim_pl >= 0 else '-$'}{abs(total_sim_pl):.2f}")
    print("========================================================\n")

if __name__ == "__main__":
    run_tape_audit()
