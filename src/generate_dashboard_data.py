import os
import json
import sqlite3
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(os.path.dirname(current_dir), 'harm_telemetry.db')
JSON_OUTPUT_PATH = os.path.join(os.path.dirname(current_dir), 'dashboard_data.json')

def fetch_and_compile_telemetry():
    if not os.path.exists(DB_PATH):
        print(f"[*] Database not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        today_str = datetime.now().strftime("%Y-%m-%d")

        # 1. Fetch Ledger Base Values
        cursor.execute("SELECT starting_settled_cash, available_settled_cash, unsettled_cash FROM account_ledger WHERE date = ?", (today_str,))
        ledger_row = cursor.fetchone()

        starting_cash = ledger_row[0] if ledger_row else 2000.00
        unsettled_cash = ledger_row[2] if ledger_row else 0.0

        # 2. Grab trades from SQLite database
        cursor.execute("""
            SELECT timestamp, ticker, direction, spot_price, exit_status, stop_loss, take_profit, net_pnl 
            FROM trades 
            ORDER BY timestamp ASC
        """)
        rows = cursor.fetchall()

        active_positions = []
        closed_trades_by_day = {}
        deployed_capital = 0.0
        floating_pnl = 0.0
        today_realized_pnl = 0.0

        # Process each trade row chronologically
        for r in rows:
            timestamp_str, ticker, direction, spot_price, exit_status = r[0], r[1], r[2], r[3], r[4]
            stop_loss = r[5] if len(r) > 5 else None
            take_profit = r[6] if len(r) > 6 else None
            net_pnl = r[7] if len(r) > 7 and r[7] is not None else 0.0
            
            spot_price = float(spot_price) if spot_price is not None else 0.0
            
            try:
                date_key = timestamp_str.split(" ")[0]
            except Exception:
                date_key = today_str

            trade_obj = {
                "timestamp": timestamp_str,
                "ticker": ticker,
                "direction": direction,
                "spot_price": spot_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "net_pnl": net_pnl,
                "exit_status": exit_status
            }

            if exit_status == "ACTIVE":
                # For ACTIVE options positions:
                # spot_price stores option premium cost ($1.60 / $2.48)
                opt_premium = spot_price
                
                # Active PnL stays 0.0 until live delta ticks are calculated or trade closes
                calc_floating = 0.0 if (net_pnl is None or net_pnl == 0.0) else net_pnl
                
                trade_obj["net_pnl"] = calc_floating
                active_positions.append(trade_obj)
                deployed_capital += opt_premium
                floating_pnl += calc_floating
            else:
                if date_key not in closed_trades_by_day:
                    closed_trades_by_day[date_key] = {
                        "trades": [],
                        "daily_pnl": 0.0
                    }
                
                closed_trades_by_day[date_key]["trades"].append(trade_obj)
                closed_trades_by_day[date_key]["daily_pnl"] += net_pnl
                
                if date_key == today_str:
                    today_realized_pnl += net_pnl

        # Calculate effective available settled cash dynamically
        effective_available = starting_cash - deployed_capital

        # Update account_ledger with latest calculated available settled cash
        cursor.execute("UPDATE account_ledger SET available_settled_cash = ? WHERE date = ?", (round(effective_available, 2), today_str))
        conn.commit()
        conn.close()

        # Sort daily stats by date descending for UI display readability
        sorted_daily_stats = []
        cumulative_pnl_tracker = 0.0
        
        for date in sorted(closed_trades_by_day.keys()):
            day_data = closed_trades_by_day[date]
            cumulative_pnl_tracker += day_data["daily_pnl"] 
            sorted_daily_stats.append({
                "date": date,
                "closed_count": len(day_data["trades"]),
                "daily_pnl": round(day_data["daily_pnl"], 2),
                "trades": day_data["trades"],
                "cumulative_pnl_to_date": round(cumulative_pnl_tracker, 2)
            })
        
        sorted_daily_stats.reverse() # Newest days first

        payload = {
            "summary": {
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_active_count": len(active_positions),
                "total_closed_days": len(sorted_daily_stats),
                "floating_pnl": round(floating_pnl, 2),
                "today_realized_pnl": round(today_realized_pnl, 2)
            },
            "ledger": {
                "starting_settled_cash": starting_cash,
                "available_settled_cash": round(effective_available, 2),
                "deployed_capital": round(deployed_capital, 2),
                "unsettled_cash": round(unsettled_cash, 2)
            },
            "active_positions": active_positions,
            "daily_closed_history": sorted_daily_stats
        }

        # Safe atomic swap write
        temp_path = f"{JSON_OUTPUT_PATH}.tmp"
        with open(temp_path, 'w') as f:
            json.dump(payload, f, indent=4)
        os.replace(temp_path, JSON_OUTPUT_PATH)
        
        print(f"[✓] Compiled dashboard: {len(active_positions)} active flights (${deployed_capital:,.2f} deployed) | Available Cash: ${effective_available:,.2f}")

    except sqlite3.OperationalError as e:
        print(f"[🚨] DB Operational Error: {e}")

if __name__ == '__main__':
    fetch_and_compile_telemetry()
