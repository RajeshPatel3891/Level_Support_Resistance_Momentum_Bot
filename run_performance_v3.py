import sqlite3

def run_performance():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    # We select all records, then process the PnL calculation in Python to avoid SQL parsing complexity
    cursor.execute("SELECT ticker, exit_status FROM trades WHERE is_live = 0")
    rows = cursor.fetchall()
    
    performance = {}
    
    for ticker, status in rows:
        if ticker not in performance:
            performance[ticker] = {"wins": 0, "losses": 0, "total": 0}
            
        performance[ticker]["total"] += 1
        # Simple heuristic: if it contains 'TAKE_PROFIT', it's a win
        if "TAKE_PROFIT" in status:
            performance[ticker]["wins"] += 1
        elif "STOP_LOSS" in status:
            performance[ticker]["losses"] += 1
            
    print("\n" + "="*60)
    print(f" HARM.AI // PERFORMANCE AUDIT (Historical) ")
    print("="*60)
    print(f"{'Ticker':<10} | {'Trades':<10} | {'Win Rate':<15}")
    print("-" * 60)
    
    for ticker, data in performance.items():
        wr = (data["wins"] / data["total"]) * 100 if data["total"] > 0 else 0
        print(f"{ticker:<10} | {data['total']:<10} | {wr:>+13.1f}%")
        
    print("="*60 + "\n")
    conn.close()

if __name__ == "__main__":
    run_performance()
