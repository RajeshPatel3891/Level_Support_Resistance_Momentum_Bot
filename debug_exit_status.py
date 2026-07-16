import sqlite3
conn = sqlite3.connect("harm_telemetry.db")
cursor = conn.cursor()
# List every unique status found in the database
cursor.execute("SELECT DISTINCT exit_status FROM trades")
rows = cursor.fetchall()
print("Found these unique exit_status values:")
for r in rows:
    print(f" -> {r[0]}")
conn.close()
