import sqlite3
import time

def evaluate_gex_exits():
    try:
        conn = sqlite3.connect("harm_telemetry.db", timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT id, ticker, spot_price, entry_price FROM trades WHERE exit_status = 'ACTIVE'")
        active = cursor.fetchall()
        
        if not active:
            print("[⚙️ GEX MONITOR] Scanning... 0 active trades pending GEX exit.")
        else:
            for trade in active:
                t_id, ticker, current_price, entry_price = trade
                print(f"[⚙️ GEX MONITOR] Tracking ID {t_id} ({ticker}) | Spot: ${current_price} | Entry: ${entry_price}")
        
        conn.close()
    except Exception as e:
        print(f"[-] GEX Exit Monitor Error: {e}")

if __name__ == "__main__":
    print("[⚙️] GEX Exit Monitor Active Routine Initialized.")
    while True:
        evaluate_gex_exits()
        time.sleep(10)
