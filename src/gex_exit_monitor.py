import sqlite3
import time
import json
import os
from datetime import datetime

MANIFEST_PATH = "trading_levels.json"
MTTP_MAX_MINUTES = 45  # Max time allowed in trade before MTTP time-decay exit

def get_live_spot(ticker):
    """Safely fetch live spot price from trading_levels.json root manifest."""
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r") as f:
                data = json.load(f)
            val = data.get(ticker, {})
            spot = val.get("spot", val.get("last_price", 0.0))
            if spot and float(spot) > 0:
                return float(spot)
        except Exception:
            pass
    return 0.0

def ensure_schema():
    """Ensure required schema columns exist to prevent operational execution halts."""
    try:
        conn = sqlite3.connect("harm_telemetry.db", timeout=10.0)
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE trades ADD COLUMN exit_timestamp TEXT")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
        conn.close()
    except Exception as e:
        print(f"[-] Schema verification warning: {e}")

def evaluate_gex_exits():
    try:
        conn = sqlite3.connect("harm_telemetry.db", timeout=10.0)
        cursor = conn.cursor()
        
        # Select active trade schema fields
        cursor.execute("SELECT id, ticker, spot_price, entry_price, direction, timestamp FROM trades WHERE exit_status = 'ACTIVE'")
        active = cursor.fetchall()
        
        if not active:
            print("[⚙️ GEX/MTTP MONITOR] Scanning... 0 active trades pending GEX exit.")
        else:
            now = datetime.now()
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            for trade in active:
                t_id, ticker, spot_price, entry_price, direction, ts_str = trade
                
                # Real-time spot lookup falling back to DB record
                live_spot = get_live_spot(ticker) or float(spot_price or entry_price or 0.0)
                trade_dir = str(direction).upper() if direction else "OPTION"
                
                # Parse timestamp and compute elapsed minutes
                elapsed_minutes = 0.0
                if ts_str:
                    try:
                        clean_ts = str(ts_str).split('.')[0].replace('T', ' ')
                        entry_dt = datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
                        elapsed_minutes = round((now - entry_dt).total_seconds() / 60.0, 1)
                    except Exception:
                        pass

                # Unified telemetry tracking output
                print(f"[⚙️ MTTP MONITOR] Tracking ID {t_id} ({ticker} {trade_dir}) | Spot: ${live_spot:.2f} | Entry: ${entry_price} | Time-in-Trade: {elapsed_minutes}m/{MTTP_MAX_MINUTES}m")
                
                # Rule 1: MTTP Maximum Time-in-Trade Expiration Trigger
                if elapsed_minutes >= MTTP_MAX_MINUTES:
                    exit_reason = f"MTTP_TIME_EXPIRED_{MTTP_MAX_MINUTES}M"
                    
                    # Update exit_status AND record explicit exit_timestamp for dashboard accounting
                    cursor.execute(
                        "UPDATE trades SET exit_status = ?, exit_price = ?, exit_timestamp = ? WHERE id = ?", 
                        (exit_reason, live_spot, now_str, t_id)
                    )
                    conn.commit()
                    print(f"🚨 [MTTP EXIT TRIGGERED] ID {t_id} ({ticker}) exceeded {MTTP_MAX_MINUTES}m threshold -> Force Exit logged at {now_str}")

        conn.close()
    except Exception as e:
        print(f"[-] GEX Exit Monitor Error: {e}")

if __name__ == "__main__":
    ensure_schema()
    print("[⚙️] GEX & MTTP Active Exit Monitor Routine Initialized.")
    while True:
        evaluate_gex_exits()
        time.sleep(10)
