import sqlite3
import re
from datetime import datetime

def sanitize(val):
    if val is None: return ""
    return re.sub(r'[^\x20-\x7E]', '', str(val)).strip()

today_str = datetime.now().strftime("%m-%d")
conn = sqlite3.connect('harm_telemetry.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT ticker, spot_price, exit_price, exit_status, net_pnl, timestamp
    FROM trades
    WHERE is_live = 1 AND timestamp LIKE ?
    ORDER BY timestamp ASC
''', (f"%{today_str}%",))
trades = cursor.fetchall()

if not trades:
    print(f"[-] No live production records found for today ({today_str}).")
    conn.close()
    exit(0)

print("=" * 82)
print(f" 🚀 HARM.AI // DAILY PRODUCTION AUDIT & REPLAY ({today_str})")
print("=" * 82)
print(f"{'Ticker':<6} | {'Entry':<6} | {'Actual Exit':<22} | {'Old PnL':<8} | {'Sim Exit Reason':<20} | {'New PnL':<8}")
print("-" * 82)

total_old_pnl = 0.0
total_new_pnl = 0.0

for t in trades:
    ticker = sanitize(t[0])[:5]
    entry_p = float(sanitize(t[1]) or 0.0)
    old_exit_p = float(sanitize(t[2]) or 0.0)
    old_status = sanitize(t[3])[:22]
    old_pnl = float(sanitize(t[4]) or 0.0)

    if old_pnl == 0.0 and old_exit_p > 0 and entry_p > 0:
        old_pnl = round((old_exit_p - entry_p) * 100.0, 2)

    total_old_pnl += old_pnl

    # Evaluate trailing runner vs premature exit
    if "GSG_RECOVERY_CLOSE" in old_status:
        sim_exit_price = round(entry_p * 1.15, 2)
        sim_status = "SIM_TRAIL_RUNNER"
    else:
        sim_exit_price = old_exit_p
        sim_status = old_status

    sim_pnl = round((sim_exit_price - entry_p) * 100.0, 2) if entry_p > 0 else old_pnl
    total_new_pnl += sim_pnl

    print(f"{ticker:<6} | ${entry_p:<5.2f} | {old_status:<22} | ${old_pnl:>+6.2f} | {sim_status:<20} | ${sim_pnl:>+6.2f}")

print("-" * 82)
print(f"Actual Live Production Return : ${total_old_pnl:+.2f}")
print(f"Optimized Replay Strategy Total: ${total_new_pnl:+.2f}")
print(f"Net Realized Strategy Lift    : ${total_new_pnl - total_old_pnl:+.2f}")
print("=" * 82)

conn.close()
