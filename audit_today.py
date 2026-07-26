import sqlite3

with sqlite3.connect('harm_telemetry.db') as conn:
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('''
        SELECT id, ticker, strategy, direction, support_level, spot_price, entry_price, exit_price,
               stop_loss, take_profit, distance, allowed_dist, proximity_score, exit_status,
               net_pnl, is_live, cso_cleared, cso_notes, shares,
               datetime(timestamp, '-4 hours') as edt_time
        FROM trades
        WHERE DATE(datetime(timestamp, '-4 hours')) = DATE('now', '-4 hours')
        ORDER BY id DESC
    ''')
    rows = c.fetchall()

print("=" * 95)
print("🦅 HARM.AI // DEEP SESSION TELEMETRY & RISK PROFILE AUDIT (EDT)")
print("=" * 95 + "\n")

if rows:
    for r in rows:
        entry = float(r["entry_price"]) if r["entry_price"] is not None else 0.0
        exit_p = float(r["exit_price"]) if r["exit_price"] is not None else 0.0
        pnl = float(r["net_pnl"]) if r["net_pnl"] is not None else 0.0
        contracts = float(r["shares"]) if r["shares"] is not None else 1.0
        sl = float(r["stop_loss"]) if r["stop_loss"] is not None else 0.0
        tp = float(r["take_profit"]) if r["take_profit"] is not None else 0.0
        dist = float(r["distance"]) if r["distance"] is not None else 0.0
        allowed = float(r["allowed_dist"]) if r["allowed_dist"] is not None else 0.0
        score = float(r["proximity_score"]) if r["proximity_score"] is not None else 0.0
        
        mode = "LIVE" if r["is_live"] else "SIM/PAPER"
        cso_notes = r["cso_notes"] if r["cso_notes"] else "None recorded"
        supp_lvl = f"${float(r['support_level']):.2f}" if r["support_level"] is not None else "N/A"

        print(f"[{r['edt_time']}] Trade ID: {r['id']:<4} | {r['ticker']:<5} ({r['direction']}) | Mode: {mode}")
        print(f"   Strategy: {r['strategy']:<18} | Key Level Ref: {supp_lvl}")
        print(f"   Contracts: {contracts:<4.1f} | Entry: ${entry:.2f} | Exit: ${exit_p:.2f} | PnL: ${pnl:+.2f}")
        print(f"   🛡️ Risk Profile  : Stop Loss: ${sl:.2f} | Target: ${tp:.2f} | Prox Score: {score:.2f}")
        print(f"   📐 Level Proximity: Dist: ${dist:.2f} (Max Allowed: ${allowed:.2f})")
        print(f"   🎯 CSO Exit Reason: Status: {r['exit_status']} | Cleared: {r['cso_cleared']}")
        print(f"   📝 CSO Notes      : {cso_notes}")
        print("-" * 95)
else:
    print("[!] No trades found for today's EDT session.")
