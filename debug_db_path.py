import sqlite3
import os

def debug():
    db_path = os.path.abspath("harm_telemetry.db")
    print(f"\n[*] Debugging Connection to: {db_path}")
    
    if not os.path.exists(db_path):
        print("[!] FATAL: File does not exist at this path!")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. List all tables to see if 'trades' even exists here
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"[*] Tables found in this file: {tables}")
    
    if not tables:
        return

    # 2. Count rows in the first table found
    table_name = tables[0][0]
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"[*] Total rows in table '{table_name}': {count}")
    
    # 3. Print first 3 rows
    cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
    print(f"[*] First 3 rows: {cursor.fetchall()}")
    
    conn.close()

if __name__ == "__main__":
    debug()
