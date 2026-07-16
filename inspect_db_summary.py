import sqlite3
from collections import Counter

def analyze_db_holistic():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    # Get total count
    cursor.execute("SELECT COUNT(*) FROM trades")
    total = cursor.fetchone()[0]
    
    # Get count by date
    cursor.execute("SELECT DATE(timestamp), COUNT(*) FROM trades GROUP BY DATE(timestamp)")
    rows = cursor.fetchall()
    
    print("\n" + "="*50)
    print(f" HARM.AI // DATABASE HOLISTIC SUMMARY ")
    print("="*50)
    print(f"Total Records Found: {total}")
    print("-" * 50)
    print(f"{'Date':<15} | {'Trade Count':<10}")
    print("-" * 50)
    
    for date, count in rows:
        print(f"{date:<15} | {count:<10}")
    print("="*50 + "\n")
    
    conn.close()

if __name__ == "__main__":
    analyze_db_holistic()
