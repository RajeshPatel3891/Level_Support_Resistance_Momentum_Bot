import sqlite3
import csv
import glob
import os

DB_FILE = "harm_telemetry.db"
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Re-init schema to be safe
cursor.execute("""
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        strategy TEXT NOT NULL,
        direction TEXT NOT NULL,
        support_level REAL,
        spot_price REAL,
        exit_price REAL,
        stop_loss REAL,
        take_profit REAL,
        distance REAL,
        allowed_dist REAL,
        proximity_score REAL,
        exit_status TEXT,
        net_pnl REAL,
        is_live INTEGER DEFAULT 1
    )
""")

for filepath in glob.glob("*_audit.csv"):
    ticker = filepath.split('_')[0]
    print(f"[*] Ingesting {filepath}...")
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        next(reader, None) # Skip header
        for row in reader:
            if not row or len(row) < 5: continue
            # Row Layout: Timestamp, Price, Action, Conviction, Result, Notes
            ts, price, action, conv, res, notes = row
            if action in ["EXIT", "FORCE_CLOSE"]:
                cursor.execute("""
                    INSERT INTO trades (ticker, timestamp, strategy, direction, exit_status, net_pnl, is_live)
                    VALUES (?, ?, 'HISTORICAL', 'LONG', ?, 0.0, 0)
                """, (ticker, ts, res))
conn.commit()
conn.close()
print("[✓] Historical audit files successfully ingested with correct timestamps.")
