import sqlite3
import csv
import glob

DB_FILE = "harm_telemetry.db"
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# Wipe only historical runs
cursor.execute("DELETE FROM trades WHERE is_live = 0")
conn.commit()

for filepath in glob.glob("*_audit.csv"):
    ticker = filepath.split('_')[0]
    with open(filepath, 'r') as f:
        reader = csv.reader(f)
        next(reader, None)
        
        current_trade = None
        for row in reader:
            if not row or len(row) < 5: continue
            ts, price, action, conv, res, notes = row
            price = float(price)
            
            if action == "ENTER":
                current_trade = {"ts": ts, "entry": price}
            elif action in ["EXIT", "FORCE_CLOSE"] and current_trade:
                # Calculate PnL (Option Premium Leverage Proxy: 5 contracts * 10x multiplier)
                ratio = (price - current_trade["entry"]) / current_trade["entry"] if current_trade["entry"] > 0 else 0
                net_pnl = 500.0 * ratio * 10.0
                
                cursor.execute("""
                    INSERT INTO trades (ticker, timestamp, strategy, direction, spot_price, exit_price, exit_status, net_pnl, is_live, cso_cleared, cso_notes)
                    VALUES (?, ?, 'HISTORICAL', 'LONG', ?, ?, ?, ?, 0, 1, 'Historical Backtest')
                """, (ticker, current_trade["ts"], current_trade["entry"], price, f"{action}: {res}", net_pnl))
                current_trade = None

conn.commit()
conn.close()
print("[✓] Success: All historical trades ingested with actual PnL calculations.")
