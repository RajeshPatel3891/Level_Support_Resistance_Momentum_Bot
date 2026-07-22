import sqlite3
import os
from datetime import datetime

DB_FILE = 'harm_telemetry.db'

def audit_account_cash():
    if not os.path.exists(DB_FILE):
        print(f"[!] Error: {DB_FILE} not found.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Fetch Ledger Base Values
    cursor.execute("SELECT starting_settled_cash, available_settled_cash, unsettled_cash FROM account_ledger WHERE date = ?", (today_str,))
    ledger_row = cursor.fetchone()

    starting_cash = ledger_row[0] if ledger_row else 2000.00
    unsettled = ledger_row[2] if ledger_row else 0.0

    # 2. Calculate Capital Tied Up in Currently Active Positions
    cursor.execute("SELECT spot_price FROM trades WHERE exit_status = 'ACTIVE'")
    active_trades = cursor.fetchall()
    deployed_capital = sum(row[0] for row in active_trades if row[0] is not None)

    # 3. Calculate Realized PnL for Today's Closed Positions
    cursor.execute("SELECT net_pnl FROM trades WHERE exit_status != 'ACTIVE' AND timestamp LIKE ?", (f"{today_str}%",))
    closed_trades = cursor.fetchall()
    total_realized_pnl = sum(row[0] for row in closed_trades if row[0] is not None)

    # 4. Compute Dynamic Effective Settled Cash
    effective_available = starting_cash - deployed_capital

    # 5. Automatically Persist Synced Balance Back to Database
    cursor.execute("UPDATE account_ledger SET available_settled_cash = ? WHERE date = ?", (effective_available, today_str))
    conn.commit()
    conn.close()

    print("=" * 60)
    print(f"📊 HARM.AI CASH LEDGER AUDIT ({today_str})")
    print("=" * 60)
    print(f"💵 Starting Day Settled Cash : ${starting_cash:,.2f}")
    print(f"🟢 Available Settled Cash   : ${effective_available:,.2f}  (Free funds available for new trades)")
    print(f"🔒 Capital Deployed Active  : ${deployed_capital:,.2f}  ({len(active_trades)} open positions)")
    print(f"⏳ Unsettled Funds (T+1)     : ${unsettled:,.2f}  (Settles next business day)")
    print(f"📈 Today's Realized PnL     : ${total_realized_pnl:,.2f}")
    print("=" * 60)

if __name__ == "__main__":
    audit_account_cash()
