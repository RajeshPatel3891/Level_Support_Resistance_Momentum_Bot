import sqlite3
import re

def sanitize(val):
    if val is None:
        return ""
    # Strip non-printable ASCII and hidden UTF-8 control chars (like \xa0, \r, \n)
    s = str(val)
    s = re.sub(r'[^\x20-\x7E]', '', s)
    return s.strip()

conn = sqlite3.connect('harm_telemetry.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT 
        timestamp, 
        ticker, 
        exit_status, 
        spot_price, 
        exit_price, 
        net_pnl,
        shares
    FROM trades 
    WHERE is_live = 1 
    ORDER BY timestamp DESC
''')
rows = cursor.fetchall()

clean_rows = []
for r in rows:
    ts = sanitize(r[0])[5:19]
    ticker = sanitize(r[1])[:5]
    status = sanitize(r[2])[:24]
    
    try:
        spot = float(sanitize(r[3]) or 0.0)
    except ValueError:
        spot = 0.0
        
    try:
        exit_p = float(sanitize(r[4]) or 0.0)
    except ValueError:
        exit_p = 0.0
        
    try:
        pnl = float(sanitize(r[5]) or 0.0)
    except ValueError:
        pnl = 0.0

    try:
        shares = float(sanitize(r[6]) or 1.0)
    except ValueError:
        shares = 1.0

    # Calculate contract PnL if database value is 0.0
    if pnl == 0.0 and exit_p > 0 and spot > 0:
        pnl = round((exit_p - spot) * 100.0 * shares, 2)
        
    clean_rows.append((ts, ticker, status, pnl))

conn.close()

if clean_rows:
    total = len(clean_rows)
    wins = sum(1 for r in clean_rows if r[3] > 0)
    total_pnl = sum(r[3] for r in clean_rows)
    win_rate = (wins / total) * 100.0 if total > 0 else 0.0

    print("=" * 68)
    print(" 🚀 HARM.AI // PURE PRODUCTION EXECUTION AUDIT")
    print("=" * 68)
    print("Total Prod Trades : " + str(total))
    print("Prod Win Rate     : " + f"{win_rate:.2f}% ({wins}/{total} Wins)")
    print("Net Prod Return   : " + f"${total_pnl:+.2f}")
    print("-" * 68)
    print(f"{'Timestamp':<14} | {'Ticker':<6} | {'Outcome':<24} | {'Net PnL':<10}")
    print("-" * 68)
    for ts, ticker, status, pnl in clean_rows:
        pnl_str = f"${pnl:+.2f}"
        print(f"{ts:<14} | {ticker:<6} | {status:<24} | {pnl_str:<10}")
    print("=" * 68)
else:
    print("[-] No live records found.")
