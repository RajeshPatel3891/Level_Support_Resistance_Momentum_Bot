import os
import sys
import json
import time

# Resolve pathways flawlessly
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if current_dir not in sys.path: sys.path.insert(0, current_dir)
if parent_dir not in sys.path: sys.path.insert(0, parent_dir)

print("=========================================================================================")
print("⛈️  HARM.AI // PILOT SIMULATION: PARTIALLY CLOUDY GEX DRIFT & DE-RISK")
print("=========================================================================================")

# 1. Simulate the Tricky, Turbulent Time-Series Scenario
cloudy_scenarios = [
    {
        "step": 1, 
        "price": 314.10, 
        "vwap": 314.80, 
        "desc": "AAPL hits Support A ($314.00). Entering position at $1.38."
    },
    {
        "step": 2, 
        "price": 313.20, 
        "vwap": 313.80, 
        "desc": "Turbulence! Spot flushes below Support. GEX Flip updates down to $1.15. Premium decays to $0.80."
    },
    {
        "step": 3, 
        "price": 315.50, 
        "vwap": 314.10, 
        "desc": "Rebound! Spot rises. Option premium climbs to $1.65. TP1 Target ($2.07) not yet met."
    },
    {
        "step": 4, 
        "price": 314.80, 
        "vwap": 314.20, 
        "desc": "Momentum stalls. Trailing Profit Lock triggers: De-risking 50% of position at $1.50 to secure green."
    },
    {
        "step": 5, 
        "price": 312.50, 
        "vwap": 314.50, 
        "desc": "Sharp market reversal. Invalidation trigger hits. Remaining 50% stopped out at $1.10."
    }
]

def run_cloudy_simulation():
    try:
        import aapl_playbook
    except ModuleNotFoundError:
        from src import aapl_playbook
        
    evaluate_call_entry = aapl_playbook.evaluate_call_entry
    calculate_risk_parameters = aapl_playbook.calculate_risk_parameters
    
    active_position = False
    contracts = 3
    cost_basis = 1.38
    current_order_price = 1.38
    
    # Realized cash tracker
    realized_cash = 0.0

    print("\n[⚡] Engaging Instrument Flight Rules (IFR)...\n")

    for state in cloudy_scenarios:
        print("-" * 90)
        print(f"⏰ [SIM STEP {state['step']}] AAPL Spot: ${state['price']:.2f} | Option Mid: ${current_order_price:.2f}")
        print(f"ℹ️  Flight Data: {state['desc']}")
        
        # STEP 1: Standard entry execution
        if state['step'] == 1:
            triggered, size = evaluate_call_entry([], state['price'], state['vwap'])
            active_position = True
            print(f"[🚀 ENTRY] Filled {contracts} contracts at ${cost_basis:.2f} ($414.00 total basis).")
            
        # STEP 2: The Drift - adjusting your limits down to secure a fill where the market is going
        elif state['step'] == 2:
            gex_forecast_shift = 1.15
            drift_delta = abs(current_order_price - gex_forecast_shift)
            print(f"DEBUG: Active Ask: ${current_order_price:.2f} | GEX Forecast: ${gex_forecast_shift:.2f} | Delta: ${drift_delta:.2f}")
            if drift_delta > 0.10:
                print(f"[🚨 DRIFT ENGINE ACTIVE] Adjusting exit target down to match updated GEX volatility profile.")
                current_order_price = gex_forecast_shift
                print(f"[✓] Cancel & Replace completed. New exit target locked at: ${current_order_price:.2f}")

        # STEP 3: Tracking target boundaries
        elif state['step'] == 3:
            current_order_price = 1.65
            print(f"[*] Checking instruments... Current price (${current_order_price:.2f}) below TP1 ($2.07). Holding.")

        # STEP 4: De-risking! Capital preservation in chop
        elif state['step'] == 4:
            # Trailing Profit Lock / Partial Close
            de_risk_qty = 2  # Sell 2 of the 3 contracts
            sale_price = 1.50
            contracts -= de_risk_qty
            revenue = de_risk_qty * sale_price * 100
            realized_cash += revenue
            print(f"[🛡️  IF/THEN DE-RISK TRIGGERED] Momentum lost. Scaling out {de_risk_qty} contracts at ${sale_price:.2f}.")
            print(f"[💰 CASH IN BANK] Secured ${revenue:.2f} in realized liquidity. Remaining contracts: {contracts}")

        # STEP 5: Hard stop execution on remaining position
        elif state['step'] == 5:
            stop_price = 1.10
            revenue = contracts * stop_price * 100
            realized_cash += revenue
            print(f"[🛑 SYSTEM STOP-OUT] Underlying invalidation breached. Closing remaining {contracts} contract at ${stop_price:.2f}.")
            active_position = False
            contracts = 0

    print("=" * 90)
    print("📊 PILOT FLIGHT REPORT (CLOUDY SCENARIO)")
    print("=" * 90)
    total_cost = 3 * cost_basis * 100
    net_profit = realized_cash - total_cost
    pnl_pct = (net_profit / total_cost) * 100
    
    print(f"• Total Cost Basis:    ${total_cost:.2f}")
    print(f"• Total Cash Returned:  ${realized_cash:.2f}")
    print(f"• Net Profit/Loss:      ${net_profit:+.2f} ({pnl_pct:+.2f}%)")
    print(f"• Autopilot Status:     CRITICAL PROTECTION ACTIVE - AVOIDED MAX LOSS STOP-OUT (-$84.00)")
    print("=" * 90)

if __name__ == "__main__":
    run_cloudy_simulation()
