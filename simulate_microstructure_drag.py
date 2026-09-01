#!/usr/bin/env python3
"""
HARM.AI // IV CRUSH & SPREAD HAIRCUT SIMULATOR
===============================================================================
Models the exact PnL degradation caused by:
1. Spread Haircut: Buying near Mid, exiting at Bid (-5% to -10% slippage tax).
2. IV Deflation: Volatility contraction reducing contract mark post-entry.
"""

import os
import sqlite3
import pandas as pd
import numpy as np

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harm_telemetry.db')

def evaluate_microstructure_impact(entry_price: float, iv_crush_pct: float = 0.08, spread_haircut_pct: float = 0.04):
    """
    Calculates net realized entry/exit prices after applying spread tax and IV deflation.
    """
    if entry_price <= 0:
        return 0.0, 0.0, 0.0

    # 1. Theoretical Mark post IV Deflation (-8% IV contraction)
    iv_adjusted_mark = entry_price * (1.0 - iv_crush_pct)
    
    # 2. Exit Price after Spread Haircut (Exiting on Bid instead of Mid)
    bid_exit_price = max(0.01, round(iv_adjusted_mark * (1.0 - spread_haircut_pct), 2))
    
    # 3. Microstructure Drag Loss ($)
    drag_pnl_loss = round((entry_price - bid_exit_price) * 100.0, 2)
    
    return iv_adjusted_mark, bid_exit_price, drag_pnl_loss

def run_simulation():
    if not os.path.exists(DB_PATH):
        print(f"[!] Database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query("SELECT ticker, entry_price, direction, strategy FROM trades", conn)
    except Exception as e:
        print(f"[!] DB Read Error: {e}")
        conn.close()
        return
    conn.close()

    print("=" * 100)
    print("🧪 HARM.AI // MICROSTRUCTURE DRAG SIMULATION (SPREAD HAIRCUT & IV CRUSH)")
    print("=" * 100)
    print(f"{'TICKER':<8} | {'ENTRY MID':<10} | {'IV MARK (-8%)':<12} | {'BID EXIT (-4%)':<14} | {'SLIPPAGE TAX ($)':<16} | {'IMPACT'}")
    print("-" * 100)

    total_drag = 0.0
    count = 0

    for idx, row in df.iterrows():
        ticker = str(row.get('ticker', 'N/A')).upper()
        entry_price = float(row.get('entry_price', 0.0) or 0.0)

        if entry_price <= 0.30:  # Skip illiquid traps
            continue

        iv_mark, bid_exit, drag_loss = evaluate_microstructure_impact(entry_price)
        total_drag += drag_loss
        count += 1

        print(f"{ticker:<8} | ${entry_price:<9.2f} | ${iv_mark:<11.2f} | ${bid_exit:<13.2f} | -${drag_loss:<15.2f} | 🔴 -$ {drag_loss:.2f}/contract")

    print("=" * 100)
    print("📊 MICROSTRUCTURE IMPACT SUMMARY:")
    print(f"  Evaluated Positions     : {count}")
    print(f"  Total Slippage + IV Drag : -${total_drag:.2f}")
    print(f"  Avg Friction Per Trade  : -${(total_drag / max(1, count)):.2f} / contract")
    print("=" * 100)

if __name__ == "__main__":
    run_simulation()
