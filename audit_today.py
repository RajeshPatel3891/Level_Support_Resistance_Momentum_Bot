import sqlite3

conn = sqlite3.connect("harm_telemetry.db")
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("""
    SELECT id, ticker, direction, entry_price, shares, exit_status, net_pnl, timestamp
    FROM trades
    WHERE timestamp LIKE '2026-07-23%' OR DATE(timestamp) = CURRENT_DATE
    ORDER BY id DESC
""")

rows = cursor.fetchall()

print("=" * 85)
print("🦅 HARM.AI // TODAY SESSION TELEMETRY AUDIT")
print("=" * 85 + "\n")

if rows:
    for r in rows:
        entry = float(r["entry_price"]) if r["entry_price"] is not None else 0.0
        pnl = float(r["net_pnl"]) if r["net_pnl"] is not None else 0.0
        contracts = float(r["shares"]) if r["shares"] is not None else 1.0
        
        ts = r["timestamp"]
        tid = r["id"]
        ticker = r["ticker"]
        direction = r["direction"]
        status = r["exit_status"]
        
        print(f"[{ts}] Trade ID: {tid:<4} | {ticker:<5} ({direction})")
        print(f"   Contracts: {contracts:<4.1f} | Option Entry: ${entry:.2f}/contract")
        print(f"   Exit Status: {status:<22} | Net PnL: ${pnl:+.2f}")
        print("-" * 85)
else:
    print("[!] No trades found for today's session.")

conn.close()
