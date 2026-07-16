import sqlite3

def run_performance():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    # Filter for ONLY completed trades
    cursor.execute("""
        SELECT ticker, COUNT(*), SUM(net_pnl) 
        FROM trades 
        WHERE exit_status LIKE 'EXIT:%' OR exit_status LIKE 'FORCE_CLOSE:%'
        GROUP BY ticker
    """)
    rows = cursor.fetchall()
    
    print("\n" + "="*60)
    print(f" HARM.AI // PERFORMANCE AUDIT (Completed Trades Only) ")
    print("="*60)
    print(f"{'Ticker':<10} | {'Trades':<10} | {'Net PnL':<15}")
    print("-" * 60)
    
    total_pnl = 0
    for ticker, count, pnl in rows:
        total_pnl += pnl
        print(f"{ticker:<10} | {count:<10} | ${pnl:>+13.2f}")
    
    print("-" * 60)
    print(f"TOTAL SYSTEM PERFORMANCE: ${total_pnl:>+13.2f}")
    print("="*60 + "\n")
    conn.close()

if __name__ == "__main__":
    run_performance()
