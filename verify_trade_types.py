import sqlite3

def verify():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    cursor.execute("SELECT exit_status, COUNT(*) FROM trades GROUP BY exit_status")
    rows = cursor.fetchall()
    
    print("\n--- Diagnostic Breakdown ---")
    for status, count in rows:
        print(f"{status:<30} : {count}")
    conn.close()

if __name__ == "__main__":
    verify()
