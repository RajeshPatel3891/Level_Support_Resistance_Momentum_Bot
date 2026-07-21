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

        # 1. Grab everything from your real trades table
        cursor.execute("""
            SELECT timestamp, ticker, direction, spot_price, exit_status 
            FROM trades 
            ORDER BY timestamp ASC
        """)
        rows = cursor.fetchall()
        conn.close()

        active_positions = []
        closed_trades_by_day = {}
        total_closed_pnl = 0.0

        # Process each trade row chronologically
        for r in rows:
            timestamp_str, ticker, direction, spot_price, exit_status = r
            spot_price = float(spot_price) if spot_price is not None else 0.0
            
            # Extract the trading day (YYYY-MM-DD)
            try:
                date_key = timestamp_str.split(" ")[0]
            except Exception:
                date_key = datetime.now().strftime("%Y-%m-%d")

            trade_obj = {
                "timestamp": timestamp_str,
                "ticker": ticker,
                "direction": direction,
                "spot_price": spot_price,
                "exit_status": exit_status
            }

            if exit_status == "ACTIVE":
                active_positions.append(trade_obj)
            else:
                # If it's a closed trade (e.g., STOP_LOSS, TAKE_PROFIT, TRAILING_STOP)
                if date_key not in closed_trades_by_day:
                    closed_trades_by_day[date_key] = {
                        "trades": [],
                        "daily_pnl": 0.0
                    }
                
                closed_trades_by_day[date_key]["trades"].append(trade_obj)
                
                # Mock or read exact close delta logic if your table doesn't log raw exit credit yet
                # For safety, let's log the transaction for your UI to parse out 
                # (You can expand this if you log a explicit 'realized_pnl' column later!)

        # Sort daily stats by date descending for UI display readability
        sorted_daily_stats = []
        cumulative_pnl_tracker = 0.0
        
        for date in sorted(closed_trades_by_day.keys()):
            day_data = closed_trades_by_day[date]
            # Accumulate historical trend lines
            cumulative_pnl_tracker += day_data["daily_pnl"] 
            sorted_daily_stats.append({
                "date": date,
                "closed_count": len(day_data["trades"]),
                "trades": day_data["trades"],
                "cumulative_pnl_to_date": round(cumulative_pnl_tracker, 2)
            })
        
        sorted_daily_stats.reverse() # Newest days first

        payload = {
            "summary": {
                "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "total_active_count": len(active_positions),
                "total_closed_days": len(sorted_daily_stats)
            },
            "active_positions": active_positions,
            "daily_closed_history": sorted_daily_stats
        }

        # Safe atomic swap write
        temp_path = f"{JSON_OUTPUT_PATH}.tmp"
        with open(temp_path, 'w') as f:
            json.dump(payload, f, indent=4)
        os.replace(temp_path, JSON_OUTPUT_PATH)
        
        print(f"[✓] Compiled dashboard: {len(active_positions)} active flights | {len(rows) - len(active_positions)} closed records parsed.")

    except sqlite3.OperationalError as e:
        print(f"[🚨] DB Operational Error: {e}")

if __name__ == '__main__':
    fetch_and_compile_telemetry()
