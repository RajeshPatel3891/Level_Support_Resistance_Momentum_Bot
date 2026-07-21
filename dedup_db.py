import sqlite3

db_path = 'harmonized_trades.db'

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check total rows before
    cursor.execute("SELECT COUNT(*) FROM harmonized_trades;")
    total_before = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(net_pnl) FROM harmonized_trades;")
    pnl_before = cursor.fetchone()[0] or 0.0

    # Delete duplicates keeping only the smallest 'id' for each unique trade signature
    cursor.execute('''
        DELETE FROM harmonized_trades
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM harmonized_trades
            GROUP BY ticker, spot_price, exit_price, exit_status
        );
    ''')

    conn.commit()

    # Check total rows after
    cursor.execute("SELECT COUNT(*) FROM harmonized_trades;")
    total_after = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(net_pnl) FROM harmonized_trades;")
    pnl_after = cursor.fetchone()[0] or 0.0

    conn.close()

    print("=" * 60)
    print("✅ DATABASE DEDUPLICATION COMPLETE")
    print(f"Total Rows Before: {total_before} | Realized PnL: ${pnl_before:,.2f}")
    print(f"Total Rows After:  {total_after}  | Realized PnL: ${pnl_after:,.2f}")
    print(f"Cleaned Up: {total_before - total_after} duplicate records")
    print("=" * 60)

except Exception as e:
    print(f"[!] Error updating database: {e}")
