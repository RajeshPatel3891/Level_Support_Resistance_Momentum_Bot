import sqlite3
import os
import sys
sys.path.append(os.getcwd())
from src.LiveBot import ACTIVE_TRADES

print("--- ENGINE MEMORY STATUS ---")
print(f"Bot Active Trades: {ACTIVE_TRADES}")

print("\n--- DATABASE REALITY CHECK ---")
conn = sqlite3.connect("harm_telemetry.db")
cursor = conn.cursor()
cursor.execute("SELECT id, ticker, exit_status, spot_price FROM trades WHERE ticker='NVDA' ORDER BY id DESC LIMIT 1")
row = cursor.fetchone()
print(f"DB Record: {row}")
conn.close()
