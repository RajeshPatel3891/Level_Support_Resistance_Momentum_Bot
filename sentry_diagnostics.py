import sqlite3
import os
import sys

db_path = "harm_telemetry.db"
if not os.path.exists(db_path):
    print(f"[!] DB not found at {os.path.abspath(db_path)}")
    sys.exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT ticker, timestamp, spot_price, strategy FROM trades WHERE exit_status = 'ACTIVE'")
rows = cursor.fetchall()
print(f"[*] Found {len(rows)} stuck trades:")
for r in rows: print(f" -> {r}")
conn.close()
