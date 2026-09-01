#!/usr/bin/env python3
"""
HARM.AI // FULL-LIFECYCLE SCALP PNL SIMULATOR (OPTIMIZED GEX MONITOR ALIGNED)
===============================================================================
Evaluates historical entries using gex_exit_monitor.py's exact optimized rules:
- 15-Minute MTTP Fast Scalp Time Exit
- +8% Peak Gain -> Lock +2% GSG Floor
- +20% / +35% Peak Gain -> Tighter Cushion Trailing Stops
- Multi-Contract Tranche Scaling at +15% Gain
- Sub-$0.50 Low-Dollar Cushion ($0.10 Floor)
"""

import os
import sqlite3
import pandas as pd
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harm_telemetry.db')

def simulate_gex_monitor_lifecycle(entry_price: float, direction: str, num_contracts: int = 1):
    """
    Simulates post-fill price path using gex_exit_monitor.py optimized rules.
    """
    if entry_price <= 0:
        return 0.0, 0.0, "INVALID_ENTRY"

    # Base stop loss definition matching optimized gex_exit_monitor
    if entry_price <= 0.50:
        initial_stop = round(max(0.02, entry_price - 0.10), 2)
    else:
        initial_stop = round(entry_price * 0.80, 2)

    tp_target = round(entry_price * 1.50, 2)  # +50% Take Profit
    
    # Simulate 15-minute fast scalp tick walk (1 step = 1 minute)
    np.random.seed(int(entry_price * 1000) % 10000)
    volatility = 0.022
    steps = 15
    price_path = [entry_price]
    
    for _ in range(steps):
        change = np.random.normal(0.0008, volatility)
        next_px = max(0.01, price_path[-1] * (1.0 + change))
        price_path.append(round(next_px, 2))

    peak_price = entry_price
    dynamic_stop = initial_stop
    exit_price = price_path[-1]
    exit_reason = "MTTP_TIME_EXPIRED_15M"
    
    accumulated_pnl = 0.0
    active_contracts = num_contracts
    is_runner = False

    for step_idx, px in enumerate(price_path[1:], start=1):
        if px > peak_price:
            peak_price = px

        pnl_pct = ((px - entry_price) / entry_price) * 100.0
        peak_pnl_pct = ((peak_price - entry_price) / entry_price) * 100.0

        # Dynamic trailing ladder matching optimized gex_exit_monitor.py
        if is_runner:
            cushion = 10.0 if peak_pnl_pct >= 50.0 else 8.0
            dynamic_stop_pct = max(3.0, peak_pnl_pct - cushion)
            dynamic_stop = round(entry_price * (1.0 + dynamic_stop_pct / 100.0), 2)
        elif peak_pnl_pct >= 35.0:
            dynamic_stop = max(dynamic_stop, round(entry_price * (1.0 + (peak_pnl_pct - 8.0) / 100.0), 2))
        elif peak_pnl_pct >= 20.0:
            dynamic_stop = max(dynamic_stop, round(entry_price * (1.0 + (peak_pnl_pct - 6.0) / 100.0), 2))
        elif peak_pnl_pct >= 8.0:  # Early +8% GSG Lock
            dynamic_stop = max(dynamic_stop, round(entry_price * 1.02, 2))

        # Tranche scaling at +15% gain for multi-contract positions
        if active_contracts > 1 and not is_runner and pnl_pct >= 15.0:
            scale_qty = active_contracts - 1
            scaled_pnl = (px - entry_price) * 100.0 * scale_qty
            accumulated_pnl += scaled_pnl
            active_contracts = 1
            is_runner = True
            continue

        # Check Exit Triggers
        if px >= tp_target:
            exit_price = tp_target
            exit_reason = "🎯 TAKE_PROFIT_50PCT"
            break

        if px <= dynamic_stop:
            exit_price = dynamic_stop
            if dynamic_stop > entry_price:
                exit_reason = f"🟢 DYNAMIC_TRAIL_STOP_TRIGGERED (${dynamic_stop:.2f})"
            else:
                exit_reason = "🔴 STOP_LOSS_TRIGGERED"
            break

    remaining_pnl = (exit_price - entry_price) * 100.0 * active_contracts
    total_pnl = round(accumulated_pnl + remaining_pnl, 2)
    
    return total_pnl, exit_price, exit_reason

def run_pnl_simulation():
    if not os.path.exists(DB_PATH):
        print(f"[!] Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        trades_df = pd.read_sql_query("SELECT * FROM trades", conn)
    except Exception as e:
        print(f"[!] Read error: {e}")
        conn.close()
        return
    conn.close()

    print("=" * 100)
    print("🧪 HARM.AI // ALIGNED OPTIMIZED SCALP PNL SIMULATION")
    print("=" * 100)
    print(f"{'TICKER':<8} | {'SIDE':<5} | {'ENTRY':<7} | {'QTY':<4} | {'EXIT PX':<7} | {'SIM PNL ($)':<11} | {'EXIT REASON'}")
    print("-" * 100)

    total_sim_pnl = 0.0
    wins = 0
    losses = 0

    for idx, row in trades_df.iterrows():
        ticker = str(row.get('ticker', 'N/A')).upper()
        direction = str(row.get('direction', 'CALL')).upper()
        entry_price = float(row.get('entry_price', 0.0) or 0.0)

        if entry_price <= 0.30:  # Skip illiquid traps rejected at Gate 3
            continue

        num_contracts = 2 if idx % 3 == 0 else 1
        pnl, exit_px, reason = simulate_gex_monitor_lifecycle(entry_price, direction, num_contracts)
        total_sim_pnl += pnl

        if pnl > 0:
            wins += 1
            pnl_str = f"+${pnl:.2f}"
        else:
            losses += 1
            pnl_str = f"-${abs(pnl):.2f}"

        print(f"{ticker:<8} | {direction:<5} | ${entry_price:<6.2f} | {num_contracts:<4} | ${exit_px:<6.2f} | {pnl_str:<11} | {reason}")

    print("=" * 100)
    print(f"📊 OPTIMIZED SIMULATED PNL SUMMARY:")
    print(f"  Executed Scalps Evaluated : {wins + losses}")
    print(f"  Win / Loss Ratio          : {wins} W / {losses} L ({round(wins/max(1, wins+losses)*100, 1)}% Win Rate)")
    print(f"  Aggregate Net PnL         : ${total_sim_pnl:+.2f}")
    print("=" * 100)

if __name__ == "__main__":
    run_pnl_simulation()
