import sqlite3
import json
import os

DB_PATH = "harm_telemetry.db"
OUTPUT_PATH = "dashboard_data.json"

def generate_data():
    if not os.path.exists(DB_PATH):
        print("[!] Database not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM trades ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    active_trades = []
    closed_trades = []
    total_realized_pnl = 0.0

    for row in rows:
        d = dict(row)
        entry = float(d.get("entry_price", d.get("spot_price", 0.0) or 0.0))
        exit_px = float(d.get("exit_price", 0.0) or 0.0)
        shares = int(d.get("shares", 1) or 1)
        
        status = str(d.get("exit_status", "ACTIVE")).upper()
        pnl = 0.0
        if status != "ACTIVE" and exit_px > 0:
            pnl = round((exit_px - entry) * shares * 100, 2)
            total_realized_pnl += pnl

        sl = d.get("stop_loss")
        tp = d.get("take_profit")
        reason = d.get("cso_reason") or d.get("strategy") or "SMART_CSO_LIVE"

        trade_obj = {
            "id": d.get("id"),
            "ticker": d.get("ticker"),
            "direction": d.get("direction"),
            "strategy": d.get("strategy", "SMART_CSO_LIVE"),
            "entry_price": entry,
            "exit_price": exit_px,
            "stop_loss": f"${float(sl):.2f}" if sl else f"${entry * 0.80:.2f}",
            "take_profit": f"${float(tp):.2f}" if tp else f"${entry * 1.50:.2f}",
            "target": f"${float(tp):.2f}" if tp else f"${entry * 1.50:.2f}",
            "cso_reason": reason,
            "exit_status": status,
            "timestamp": d.get("timestamp"),
            "occ_symbol": d.get("occ_symbol", ""),
            "realized_pnl": pnl
        }

        if status == "ACTIVE":
            active_trades.append(trade_obj)
        else:
            closed_trades.append(trade_obj)

    data = {
        "active_trades": active_trades,
        "closed_trades": closed_trades,
        "total_realized_closed": round(total_realized_pnl, 2)
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[✓] Re-compiled {len(active_trades)} active, {len(closed_trades)} closed. Realized PnL: ${total_realized_pnl:.2f}")

if __name__ == "__main__":
    generate_data()
