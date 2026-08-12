import sqlite3
import os

DB_PATH = "harm_telemetry.db"

if not os.path.exists(DB_PATH):
    print(f"[!] Database {DB_PATH} not found.")
    exit(1)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 1. Update trades with non-zero exit_price to CLOSED status and calculate net_pnl
cursor.execute("""
    UPDATE trades 
    SET exit_status = 'CLOSED',
        net_pnl = ROUND((COALESCE(exit_price, 0.0) - COALESCE(entry_price, spot_price, 0.0)) * COALESCE(shares, 1) * 100.0, 2),
        stop_loss = COALESCE(stop_loss, ROUND(COALESCE(entry_price, spot_price, 0.0) * 0.80, 2)),
        take_profit = COALESCE(take_profit, ROUND(COALESCE(entry_price, spot_price, 0.0) * 1.50, 2)),
        cso_notes = COALESCE(cso_notes, 'CSO_AUTO_RISK_EXIT')
    WHERE exit_price IS NOT NULL AND exit_price > 0.0
""")

conn.commit()

# 2. Query and print tangible table output
cursor.execute("""
    SELECT 
        id, ticker, direction, strategy, 
        entry_price, exit_price, net_pnl, 
        stop_loss, take_profit, exit_status, timestamp 
    FROM trades 
    ORDER BY id DESC
""")

rows = cursor.fetchall()

print("\n" + "="*95)
print(f"{'ID':<4} | {'TICKER':<6} | {'DIR':<4} | {'ENTRY':<7} | {'EXIT':<7} | {'PNL ($)':<9} | {'STOP LOSS':<9} | {'TARGET':<9} | {'STATUS':<7}")
print("="*95)

total_realized = 0.0
for r in rows:
    pnl = r['net_pnl'] or 0.0
    if r['exit_status'] == 'CLOSED':
        total_realized += pnl
    print(f"{r['id']:<4} | {r['ticker']:<6} | {r['direction']:<4} | ${r['entry_price'] or 0.0:<6.2f} | ${r['exit_price'] or 0.0:<6.2f} | ${pnl:<+8.2f} | ${r['stop_loss'] or 0.0:<8.2f} | ${r['take_profit'] or 0.0:<8.2f} | {r['exit_status']:<7}")

print("="*95)
print(f"TOTAL REALIZED PnL (CLOSED POSITIONS): ${total_realized:+.2f}")
print("="*95 + "\n")

conn.close()
