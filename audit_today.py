import sqlite3

with sqlite3.connect('harm_telemetry.db') as conn:
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Corrects UTC to EDT and queries today's session cleanly
    c.execute('''
        SELECT id, ticker, direction, entry_price, shares, exit_price, exit_status, net_pnl, 
               datetime(timestamp, '-4 hours') as edt_time
        FROM trades
        WHERE DATE(datetime(timestamp, '-4 hours')) = DATE('now', '-4 hours')
        ORDER BY id DESC
    ''')
    rows = c.fetchall()

print("=" * 85)
print("🦅 HARM.AI // TODAY SESSION TELEMETRY AUDIT (EDT)")
print("=" * 85 + "\n")

if rows:
    for r in rows:
        entry = float(r["entry_price"]) if r["entry_price"] is not None else 0.0
        exit_p = float(r["exit_price"]) if r["exit_price"] is not None else 0.0
        pnl = float(r["net_pnl"]) if r["net_pnl"] is not None else 0.0
        contracts = float(r["shares"]) if r["shares"] is not None else 1.0

        print(f"[{r['edt_time']}] Trade ID: {r['id']:<4} | {r['ticker']:<5} ({r['direction']})")
        print(f"   Contracts: {contracts:<4.1f} | Entry: ${entry:.2f} | Exit: ${exit_p:.2f}")
        print(f"   Exit Status: {r['exit_status']:<22} | Net PnL: ${pnl:+.2f}")
        print("-" * 85)
else:
    print("[!] No trades found for today's EDT session.")
