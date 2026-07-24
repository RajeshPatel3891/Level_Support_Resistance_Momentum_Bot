import sqlite3

conn = sqlite3.connect("harm_telemetry.db")
cursor = conn.cursor()

print("==================================================")
print("🔍 AUDITING HARM_TELEMETRY.DB FOR TRADES TODAY")
print("==================================================")

# 1. Check all tables in the database
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
print(f"[*] Tables found in DB: {tables}\n")

# 2. Check for active/open positions
if "active_positions" in tables or "positions" in tables:
    table_name = "active_positions" if "active_positions" in tables else "positions"
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    print(f"📌 ACTIVE POSITIONS TABLE ({table_name}): {len(rows)} records found.")
    for r in rows:
        print(f"   -> {r}")
else:
    print("[-] No active positions table found.")

print("")

# 3. Check for closed/executed trades
if "closed_positions" in tables or "trades" in tables:
    table_name = "closed_positions" if "closed_positions" in tables else "trades"
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()
    print(f"🏁 CLOSED POSITIONS TABLE ({table_name}): {len(rows)} records found.")
    for r in rows:
        print(f"   -> {r}")
else:
    print("[-] No closed positions table found.")

print("==================================================")
conn.close()
