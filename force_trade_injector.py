import sqlite3
import sys
import os
from datetime import datetime

if len(sys.argv) < 2:
    symbol = "PLTR"
else:
    symbol = sys.argv[1].upper()

print(f"[*] Injecting active mock tracking record for {symbol} into harm_telemetry.db...")
conn = sqlite3.connect("harm_telemetry.db")

now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# PLTR closed around $132.38. Let's set up a cost basis right at $132.00, 
# a tight Stop Loss at $131.00, and a Take Profit at $135.00 to give the exit loops room to evaluate.
query = """
    INSERT INTO trades (timestamp, ticker, direction, spot_price, stop_loss, take_profit, exit_status, strategy)
    VALUES (?, ?, 'LONG', 132.00, 131.00, 135.00, 'ACTIVE', 'LEVEL_MOMENTUM');
"""

try:
    conn.execute(query, (now_str, symbol))
    conn.commit()
    print(f"[✓] Database successfully injected with active {symbol} position.")
except Exception as e:
    print(f"[-] Database injection failed: {e}")
finally:
    conn.close()
