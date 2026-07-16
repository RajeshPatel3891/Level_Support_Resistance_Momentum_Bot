import sqlite3
import csv
import glob

def force_ingest():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    # Ensure structure
    cursor.execute("CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT, timestamp TEXT, strategy TEXT, direction TEXT, exit_status TEXT, net_pnl REAL, is_live INTEGER, cso_cleared INTEGER, cso_notes TEXT)")

    files = glob.glob("*_audit.csv")
    print(f"[*] Found {len(files)} files to ingest.")
    
    for filepath in files:
        ticker = filepath.split('_')[0]
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            next(reader, None) # Skip header
            
            for row in reader:
                if len(row) < 5: continue
                ts, price, action, conv, res, notes = row
                
                # Force insert
                cursor.execute("""
                    INSERT INTO trades (ticker, timestamp, strategy, direction, exit_status, net_pnl, is_live, cso_cleared, cso_notes)
                    VALUES (?, ?, 'HISTORICAL', 'LONG', ?, 0.0, 0, 1, 'Historical')
                """, (ticker, ts, f"{action}: {res}"))
        
        conn.commit()
        print(f"[✓] Processed {ticker}")

    cursor.execute("SELECT COUNT(*) FROM trades")
    print(f"[*] Total rows after force_ingest: {cursor.fetchone()[0]}")
    conn.close()

if __name__ == "__main__":
    force_ingest()
