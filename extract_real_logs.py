import sqlite3
import json
import os
from datetime import datetime

# Direct path to your production telemetry database
DB_FILE = os.path.join(os.getcwd(), 'harm_telemetry.db')

def extract_real_data():
    if not os.path.exists(DB_FILE):
        print(f"Error: {DB_FILE} not found. Ensure this script is in the same directory as the production DB.")
        return

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        # Pulling raw, non-simulated data from the database
        cursor.execute("""
            SELECT ticker, timestamp, strategy, direction, spot_price, exit_price, net_pnl, exit_status 
            FROM trades 
            ORDER BY timestamp ASC
        """)
        rows = cursor.fetchall()

        if not rows:
            print("No trade records found in the database.")
            return

        print(f"--- EXTRACTED {len(rows)} REAL TRADES ---")
        
        # Exporting real logs to a JSON for your dashboard
        export_data = []
        for r in rows:
            export_data.append({
                "ticker": r[0],
                "time": r[1],
                "strat": r[2],
                "dir": r[3],
                "entry": r[4],
                "exit": r[5],
                "pnl": r[6],
                "status": r[7]
            })

        with open('real_session_data.json', 'w') as f:
            json.dump(export_data, f, indent=4)
        
        print("[✓] Extraction complete. File 'real_session_data.json' saved with actual production logs.")
        print(f"Total trades recovered: {len(rows)}")

    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    extract_real_data()
