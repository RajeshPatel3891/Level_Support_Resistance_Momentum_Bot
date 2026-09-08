import sqlite3, os, time
from datetime import datetime

db_path = 'harm_telemetry.db'

while True:
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            c = conn.cursor()
            c.execute("SELECT timestamp, ticker, strategy, direction, spot_price, entry_price, exit_status, execution_tag FROM trades ORDER BY timestamp DESC LIMIT 15")
            rows = c.fetchall()
            conn.close()
            
            print('\033[H\033[J' + '='*75)
            print(f'📡 LIVE TELEMETRY WATCHER: ACTIVE & RECENT TRADES (SQLite) [{datetime.now().strftime("%H:%M:%S")}]')
            print('='*75)
            if not rows:
                print('No trades found in telemetry database.')
            else:
                for r in rows:
                    print(f'{r[0]} | {r[1]:<6} | {r[2]:<18} | {r[3]:<5} | Spot: ${float(r[4]):.2f} | Entry: ${float(r[5]):.2f} | Status: {r[6]} | Tag: {r[7]}')
            print('='*75)
        except Exception as e:
            print(f'[!] DB Read Error: {e}')
    else:
        print('Telemetry DB not found.')
    time.sleep(3)
