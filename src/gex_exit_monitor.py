import sqlite3
import time

def evaluate_gex_exits():
    try:
        conn = sqlite3.connect("harm_telemetry.db", timeout=10.0)
        cursor = conn.cursor()
        cursor.execute("SELECT id, ticker, spot_price, entry_price FROM trades WHERE exit_status = 'ACTIVE'")
        active = cursor.fetchall()
        for trade in active:
            t_id, ticker, current_price, entry_price = trade
            if current_price is not None:
                safe_exit_price = current_price if current_price < 50.0 else 0.0
        conn.close()
    except Exception as e:
        print(f"[-] GEX Exit Monitor Error: {e}")

if __name__ == "__main__":
    evaluate_gex_exits()
