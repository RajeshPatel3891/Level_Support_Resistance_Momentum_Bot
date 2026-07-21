import os
import glob
import sqlite3

print("=" * 65)
print("🔍 DISCOVERING ALL SQLITE DATABASES & TABLES")
print("=" * 65)

db_files = glob.glob("**/*.db", recursive=True) + glob.glob("**/*.sqlite", recursive=True)

if not db_files:
    print("❌ No .db or .sqlite files found in current tree!")
else:
    for db in set(db_files):
        print(f"\n📂 Database File Found: {db}")
        try:
            conn = sqlite3.connect(db)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            print(f"   Tables: {tables}")
            
            for t in tables:
                if t != 'sqlite_sequence':
                    cursor.execute(f"SELECT COUNT(*) FROM {t};")
                    count = cursor.fetchone()[0]
                    print(f"   - Table '{t}' row count: {count}")
            conn.close()
        except Exception as e:
            print(f"   [!] Error inspecting {db}: {e}")

print("=" * 65)
