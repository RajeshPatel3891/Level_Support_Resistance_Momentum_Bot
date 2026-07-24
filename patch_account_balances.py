import sqlite3
from datetime import datetime

# Baseline initial balance when the system was deployed
INITIAL_BASE_CAPITAL = 2760.96  # Your baseline starting capital from 07/23

def get_account_balances(selected_date_str):
    conn = sqlite3.connect('harm_telemetry.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Sum ALL realized PnL prior to today's date
    cursor.execute("""
        SELECT COALESCE(SUM(net_pnl), 0.0) as prior_pnl 
        FROM trades 
        WHERE DATE(timestamp) < DATE(?)
    """, (selected_date_str,))
    prior_pnl = float(cursor.fetchone()['prior_pnl'])
    
    # 2. Starting capital for TODAY = Base + Lifetime Prior PnL
    starting_capital = INITIAL_BASE_CAPITAL + prior_pnl
    
    # 3. Sum realized PnL for TODAY specifically
    cursor.execute("""
        SELECT COALESCE(SUM(net_pnl), 0.0) as today_pnl 
        FROM trades 
        WHERE DATE(timestamp) = DATE(?)
    """, (selected_date_str,))
    today_realized_pnl = float(cursor.fetchone()['today_pnl'])
    
    # 4. Settled free capital = Starting Capital + Today's Realized - Currently Deployed
    deployed_capital = 0.0  # Sum active position costs if any
    settled_free = starting_capital + today_realized_pnl - deployed_capital
    
    conn.close()
    
    return {
        "starting_capital": starting_capital,      # Should show $3,430.22 for today (07/24)
        "settled_free": settled_free,              # Starts at $3,430.22 and updates live with today's PnL
        "realized_closed": today_realized_pnl       # Today's session closed PnL
    }
