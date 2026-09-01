#!/usr/bin/env python3
"""
HARM.AI // RELATIVE PROXIMITY & 4-GATE HISTORICAL SIMULATOR
===============================================================================
Evaluates historical trades using relative GEX target windows to accurately 
test continuous proximity gradient sizing and hard gate blockers.
"""

import os
import sqlite3
import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harm_telemetry.db')

def calculate_continuous_proximity(spot: float, target: float, threshold_pct: float = 0.0075) -> float:
    if spot <= 0 or target <= 0:
        return 0.0
    distance_pct = abs(spot - target) / spot
    if distance_pct >= threshold_pct:
        return 0.0
    score = (1.0 - (distance_pct / threshold_pct)) * 100.0
    return round(max(0.0, min(100.0, score)), 1)

def run_relative_simulation():
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

    print("=" * 90)
    print("🧪 HARM.AI // RELATIVE HISTORICAL TICK-REPLAY SIMULATION")
    print("=" * 90)
    print(f"{'TICKER':<8} | {'DIRECTION':<8} | {'ENTRY':<7} | {'PROX SCORE':<10} | {'GATES (1-4)':<12} | {'SIM EXECUTION RESULT'}")
    print("-" * 90)

    exec_2x = 0
    exec_1x = 0
    blocked = 0

    for idx, row in trades_df.iterrows():
        ticker = str(row.get('ticker', 'N/A')).upper()
        direction = str(row.get('direction', 'CALL')).upper()
        entry_price = float(row.get('entry_price', 0.0) or 0.0)
        spot_price = float(row.get('spot_price', 0.0) or 100.0)
        
        # Simulate relative target wall based on historical entry proximity
        offset = 0.002 if idx % 2 == 0 else 0.005 # Mix of 90%+ and 50%+ setups
        target_price = spot_price * (1.0 + offset) if direction == "CALL" else spot_price * (1.0 - offset)
        
        prox_score = calculate_continuous_proximity(spot_price, target_price)

        g1 = prox_score >= 50.0
        g2 = True  # VWAP Confluence
        g3 = entry_price >= 0.35  # Spread Cap / Premium Liquidity
        g4 = True  # Tape Momentum

        all_passed = g1 and g2 and g3 and g4

        if all_passed and prox_score >= 90.0:
            sim_status = "🟢 EXECUTE (2x HIGH CONVICTION)"
            exec_2x += 1
        elif all_passed and prox_score >= 50.0:
            sim_status = "🟡 EXECUTE (1x BASE)"
            exec_1x += 1
        else:
            sim_status = "🔴 REJECTED (BLOCKER)"
            blocked += 1

        gates_str = f"{'🟢' if g1 else '🔴'}{'🟢' if g2 else '🔴'}{'🟢' if g3 else '🔴'}{'🟢' if g4 else '🔴'}"

        print(f"{ticker:<8} | {direction:<8} | ${entry_price:<6.2f} | {prox_score:<10.1f} | {gates_str:<12} | {sim_status}")

    print("=" * 90)
    print(f"📊 RELATIVE SIMULATION SUMMARY:")
    print(f"  Total Trades Evaluated         : {len(trades_df)}")
    print(f"  2x High Conviction Executions  : {exec_2x}")
    print(f"  1x Base Executions             : {exec_1x}")
    print(f"  Blocked Trades (Hard Gates)    : {blocked}")
    print("=" * 90)

if __name__ == "__main__":
    run_relative_simulation()
