import sqlite3
import glob

db_files = list(set(glob.glob("*.db") + ["harm_telemetry.db", "trading_engine.db", "gex_telemetry.db", "trading.db"]))

required_columns = {
    "entry_price": "REAL DEFAULT 0.0",
    "shares": "INTEGER DEFAULT 0",
    "proximity_score": "REAL DEFAULT 0.0",
    "cso_notes": "TEXT DEFAULT ''",
    "cso_cleared": "INTEGER DEFAULT 0",
    "is_live": "INTEGER DEFAULT 1",
    "occ_symbol": "TEXT DEFAULT ''"
}

for db_path in db_files:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")]
        if 'trades' in tables:
            cols = [col[1] for col in cursor.execute("PRAGMA table_info(trades);")]
            for col_name, col_def in required_columns.items():
                if col_name not in cols:
                    print(f"[*] Patching schema: Adding '{col_name}' to {db_path}...")
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_def};")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[!] Warning patching {db_path}: {e}")

print("[✓] Preboot DB schema migration complete.")
