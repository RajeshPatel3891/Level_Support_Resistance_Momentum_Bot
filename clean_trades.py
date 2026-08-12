import sqlite3
import os

DB_PATH = "harm_telemetry.db"

def deduplicate_trades():
    if not os.path.exists(DB_PATH):
        print("[!] Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Purge duplicate closed trades keeping the latest entry ID per ticker/timestamp/status
    cursor.execute("""
        DELETE FROM trades 
        WHERE id NOT IN (
            SELECT MAX(id) 
            FROM trades 
            GROUP BY ticker, timestamp, exit_status, net_pnl
        ) AND exit_status != 'ACTIVE';
    """)
    
    deleted_count = cursor.rowcount
    conn.commit()
    
    # 2. Fix any null or zero net_pnl for closed trades where exit_price and entry_price exist
    cursor.execute("""
        UPDATE trades 
        SET net_pnl = ROUND((exit_price - entry_price) * 100 * shares, 2)
        WHERE exit_status != 'ACTIVE' AND (net_pnl = 0.0 OR net_pnl IS NULL) AND exit_price > 0 AND entry_price > 0;
    """)
    updated_count = cursor.rowcount
    conn.commit()
    
    conn.close()
    print(f"[✓] Maintenance Complete: Purged {deleted_count} duplicate rows and recalculated PnL for {updated_count} closed trades.")

if __name__ == "__main__":
    deduplicate_trades()
