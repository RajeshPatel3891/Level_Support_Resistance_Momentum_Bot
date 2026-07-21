import sqlite3

db_path = 'harm_telemetry.db'

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check total rows and PnL before
    cursor.execute("SELECT COUNT(*) FROM trades;")
    total_before = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(net_pnl) FROM trades WHERE exit_status != 'ACTIVE';")
    pnl_before = cursor.fetchone()[0] or 0.0

    # Delete duplicate trade records based on ticker, spot_price, exit_price, and exit_status
    cursor.execute('''
        DELETE FROM trades
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM trades
            GROUP BY ticker, spot_price, exit_price, exit_status
        );
    ''')

    conn.commit()

    # Check total rows and PnL after
    cursor.execute("SELECT COUNT(*) FROM trades;")
    total_after = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(net_pnl) FROM trades WHERE exit_status != 'ACTIVE';")
    pnl_after = cursor.fetchone()[0] or 0.0

    conn.close()

    print("=" * 65)
    print("✅ HARM_TELEMETRY.DB DEDUPLICATION COMPLETE")
    print("=" * 65)
    print(f"Total Rows Before: {total_before} | Realized PnL: ${pnl_before:,.2f}")
    print(f"Total Rows After:  {total_after}  | Realized PnL: ${pnl_after:,.2f}")
    print(f"Removed Duplicates: {total_before - total_after} records")
    print(f"Corrected Realized PnL: ${pnl_after:,.2f}")
    print("=" * 65)

except Exception as e:
    print(f"[!] Error updating harm_telemetry.db: {e}")
