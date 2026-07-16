import sqlite3
import csv
import glob

def ingest():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades") 
    
    for filepath in glob.glob("*_audit.csv"):
        ticker = filepath.split('_')[0]
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)
            
            for row in reader:
                if len(row) < 5: continue
                ts, price, action, conv, res, notes = row
                
                # We provide a default strategy for all records to satisfy the NOT NULL constraint
                cursor.execute("""
                    INSERT INTO trades (ticker, timestamp, strategy, direction, exit_status, net_pnl, is_live)
                    VALUES (?, ?, 'HISTORICAL_TEST', 'LONG', ?, 0.0, 0)
                """, (ticker, ts, f"{action}: {res}"))
        conn.commit()
    conn.close()
    print("[✓] Ingestion complete (Schema constraints satisfied).")

ingest()
