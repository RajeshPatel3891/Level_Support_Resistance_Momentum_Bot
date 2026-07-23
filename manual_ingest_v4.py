import sqlite3
import csv
import glob

DB_FILE = "harm_telemetry.db"
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# 1. Create the table structure first (including the new CSO columns)
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
        is_live INTEGER DEFAULT 1,
        cso_cleared INTEGER DEFAULT 1,
        cso_notes TEXT
    )
""")
conn.commit()

# 2. Clear old historical data (is_live=0)
# cursor.execute("# DESTRUCTIVE SQL NEUTRALIZED: DELETE FROM trades WHERE is_live = 0")
conn.commit()

for filepath in glob.glob("*_audit.csv"):
    ticker = filepath.split('_')[0]
    print(f"[*] Total Ingesting {filepath}...")
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        next(reader, None) # Skip header
        
        for row in reader:
            if not row or len(row) < 5: continue
            ts, price, action, conv, res, notes = row
            
            # Map every action into the database with default CSO clearance
            cursor.execute("""
                INSERT INTO trades (ticker, timestamp, strategy, direction, exit_status, net_pnl, is_live, cso_cleared, cso_notes)
                VALUES (?, ?, 'HISTORICAL', 'LONG', ?, 0.0, 0, 1, 'Historical Backtest')
            """, (ticker, ts, f"{action}: {res}"))

conn.commit()
conn.close()
print("[✓] Total ingestion complete. Database initialized with CSO fields and populated.")
