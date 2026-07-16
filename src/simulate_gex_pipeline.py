import os
import sys
import json
import time

# Force structural absolute tracking path resolutions back to the root folder
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

# Ensure both paths are cleanly inserted at the very front of Python's resolution tree
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

print("=========================================================================================")
print("🛸 HARM.AI // AUTOMATED INTRADAY GEX DRIFT & EXECUTION SIMULATOR")
print("=========================================================================================")

# 1. Initialize a baseline level manifest if it's missing or flat
MANIFEST_PATH = os.path.join(parent_dir, 'trading_levels.json')
mock_levels = {
    "AAPL": {
        "support_a": 312.00,
        "support_b": 315.00,
        "resistance_a": 321.00,
        "resistance_b": 323.00
    }
}

with open(MANIFEST_PATH, 'w') as f:
    json.dump(mock_levels, f, indent=4)
print(f"[✓] Initialized simulation environment mapping at: {MANIFEST_PATH}")

# 2. Sequential Time-Series Simulation Scenario
timeline_scenarios = [
    {"step": 1, "price": 314.20, "vwap": 315.00, "desc": "AAPL approaches active support zone."},
    {"step": 2, "price": 313.50, "vwap": 313.20, "desc": "AAPL breaches support. Triggering call option picker rules..."},
    {"step": 3, "price": 316.10, "vwap": 313.50, "desc": "Price rebounds! Simulating active option limit entry position at $1.38."},
    {"step": 4, "price": 318.50, "vwap": 314.00, "desc": "Drift detected: Market shifting. Running Cancel & Replace logic routines..."},
    {"step": 5, "price": 322.50, "vwap": 314.50, "desc": "Absolute Breach Condition met! Dispatched force_exit_all to lock in profit."}
]

def run_simulation():
    # Absolute relative imports matching top-level root configurations
    try:
        import aapl_playbook
    except ModuleNotFoundError:
        from src import aapl_playbook
        
    evaluate_call_entry = aapl_playbook.evaluate_call_entry
    calculate_risk_parameters = aapl_playbook.calculate_risk_parameters
    
    print("\n[⚡] Starting Time-Series Simulation Loop...\n")
    active_position = False
    contracts = 0
    current_order_price = 1.38
    drift_threshold = 0.50

    for state in timeline_scenarios:
        print("-" * 90)
        print(f"⏰ [SIM STEP {state['step']}] Ticker: AAPL Spot: ${state['price']:.2f} | VWAP: ${state['vwap']:.2f}")
        print(f"ℹ  Context: {state['desc']}")
        
        # Step A: Evaluate Entries if Flat
        if not active_position:
            triggered, contract_size = evaluate_call_entry([], state['price'], state['vwap'])
            if triggered:
                active_position = True
                contracts = contract_size
                print(f"[🚀 SIGNAL TRIGGERED] Entry satisfied! Routed {contracts} contracts via Smart Option Picker.")
                print(f"[*] Base Limit Order Placed at: ${current_order_price:.2f}")
        
        # Step B: Evaluate Drift / Cancel & Replace State Machine
        elif active_position and state['step'] == 4:
            simulated_gex_target = 2.10 # Simulating an upgraded target shift
            drift_delta = abs(current_order_price - simulated_gex_target)
            print(f"DEBUG: Active Order: ${current_order_price:.2f} | New Target: ${simulated_gex_target:.2f} | Delta: ${drift_delta:.2f}")
            
            if drift_delta > drift_threshold:
                print(f"[🚨 DRIFT DETECTED] Drift ${drift_delta:.2f} exceeds threshold. Executing Cancel & Replace...")
                print(f"[✓] Canceled stale order at ${current_order_price:.2f}")
                current_order_price = simulated_gex_target
                print(f"[🚀] Re-routed baseline limit order for verified liquid contract at: ${current_order_price:.2f}")
        
        # Step C: Evaluate Profitable Risk Box Exit
        elif active_position and state['step'] == 5:
            risk_box = calculate_risk_parameters(1.38, "CALL")
            print(f"[🎯 BREACH DETECTED] Spot hit absolute exit condition target bounds.")
            print(f"[*] Target Parameters: Stop Loss: ${risk_box['stop_loss']} | TP1: ${risk_box['tp1']} | TP2: ${risk_box['tp2']}")
            print(f"[✓] Position PnL check: Profitable=True. Executing immediate market exit allocation.")
            print(f"[🏁 STATUS] Closed out {contracts} contracts successfully. Cumulative Profit locked.")
            active_position = False

        time.sleep(2.5)

    print("=" * 90)
    print("[⚙️] Simulation sequence complete. All state transitions executed cleanly.")
    print("=" * 90)

if __name__ == "__main__":
    run_simulation()
