import sqlite3

db_path = "harm_telemetry.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

today_str = "2026-07-24"
target_starting_cash = 3430.22

# 1. Direct update to account_ledger table in SQLite for today (passing all 3 values)
cursor.execute("""
    INSERT INTO account_ledger (date, starting_settled_cash, available_settled_cash, unsettled_cash)
    VALUES (?, ?, ?, 0.0)
    ON CONFLICT(date) DO UPDATE SET
        starting_settled_cash = excluded.starting_settled_cash,
        available_settled_cash = excluded.starting_settled_cash
""", (today_str, target_starting_cash, target_starting_cash))

conn.commit()
print(f"[✓] SQLite account_ledger for {today_str} updated to ${target_starting_cash:,.2f}")

# 2. Patch dashboard_server.py fallback values
with open("dashboard_server.py", "r") as f:
    ds_code = f.read()

ds_code = ds_code.replace("starting_cash = 2500.97", "starting_cash = 3430.22")
ds_code = ds_code.replace("2500.97", "3430.22")

with open("dashboard_server.py", "w") as f:
    f.write(ds_code)
print("[✓] dashboard_server.py fallbacks updated to $3,430.22!")

conn.close()
