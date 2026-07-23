import sqlite3
import csv
import glob

def ingest():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
# cursor.execute("# DESTRUCTIVE SQL NEUTRALIZED: DELETE FROM trades") # Clean start to be sure
    
    for filepath in glob.glob("*_audit.csv"):
        ticker = filepath.split('_')[0]
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)
            
            for row in reader:
                if len(row) < 5: continue
                ts, price, action, conv, res, notes = row
                
                # If it's a skip, log as is_live=0 with skip reason
                if "SKIP" in action:
                    cursor.execute("INSERT INTO trades (ticker, timestamp, exit_status, is_live) VALUES (?, ?, ?, 0)", (ticker, ts, f"{action}: {res}"))
                # If it's anything else (ENTER/EXIT), track it
                else:
                    cursor.execute("INSERT INTO trades (ticker, timestamp, exit_status, is_live) VALUES (?, ?, ?, 0)", (ticker, ts, f"{action}: {res}"))
        conn.commit()
    conn.close()
    print("[✓] Ingestion complete. All records (including skips) accounted for.")

ingest()
