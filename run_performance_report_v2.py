import sqlite3

def run_performance():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    # Query all trades, regardless of status, to see if they are actually in the DB
    cursor.execute("SELECT ticker, exit_status, net_pnl FROM trades WHERE is_live = 0 LIMIT 20")
    raw_data = cursor.fetchall()
    print("[*] First 20 historical rows in DB:", raw_data)

    # Simplified Performance Query
    cursor.execute("""
        SELECT ticker, COUNT(*), SUM(net_pnl) 
        FROM trades 
        WHERE is_live = 0
        GROUP BY ticker
    """)
    rows = cursor.fetchall()
    
    print("\n" + "="*60)
    print(f" HARM.AI // PERFORMANCE AUDIT (All Historical Rows) ")
    print("="*60)
    print(f"{'Ticker':<10} | {'Count':<10} | {'Sum PnL':<15}")
    print("-" * 60)
    
    total_pnl = 0
    for ticker, count, pnl in rows:
        total_pnl += (pnl or 0)
        print(f"{ticker:<10} | {count:<10} | ${pnl or 0:>+13.2f}")
    
    print("-" * 60)
    print(f"TOTAL SYSTEM PERFORMANCE: ${total_pnl:>+13.2f}")
    print("="*60 + "\n")
    conn.close()

if __name__ == "__main__":
    run_performance()
