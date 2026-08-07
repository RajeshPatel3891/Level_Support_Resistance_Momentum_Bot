import sqlite3
import glob

# Search both root AND subdirectories recursively (e.g. src/harm_telemetry.db)
db_files = list(set(
    glob.glob("*.db") + 
    glob.glob("**/*.db", recursive=True) + 
    ["harm_telemetry.db", "src/harm_telemetry.db", "trading_engine.db", "gex_telemetry.db", "trading.db"]
))

required_columns = {
    "entry_price": "REAL DEFAULT 0.0",
    "shares": "INTEGER DEFAULT 0",
    "proximity_score": "REAL DEFAULT 0.0",
    "cso_notes": "TEXT DEFAULT ''",
    "cso_cleared": "INTEGER DEFAULT 0",
    "is_live": "INTEGER DEFAULT 1",
    "occ_symbol": "TEXT DEFAULT ''"
}

account_ledger_sql = """
CREATE TABLE IF NOT EXISTS account_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    balance REAL DEFAULT 10000.0,
    available_cash REAL DEFAULT 10000.0,
    deployed_capital REAL DEFAULT 0.0,
    net_pnl REAL DEFAULT 0.0
);
"""

for db_path in db_files:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        tables = [row[0] for row in cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")]
        
        # 1. Patch trades table columns
        if 'trades' in tables:
            cols = [col[1] for col in cursor.execute("PRAGMA table_info(trades);")]
            for col_name, col_def in required_columns.items():
                if col_name not in cols:
                    print(f"[*] Patching schema: Adding '{col_name}' to {db_path}...")
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_def};")
                    
        # 2. Patch or create account_ledger table
        if 'account_ledger' not in tables:
            print(f"[*] Initializing missing table 'account_ledger' in {db_path}...")
            cursor.execute(account_ledger_sql)
            cursor.execute("INSERT INTO account_ledger (balance, available_cash, deployed_capital, net_pnl) VALUES (10000.0, 10000.0, 0.0, 0.0);")

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[!] Warning patching {db_path}: {e}")

print("[✓] Preboot DB schema & ledger migration complete across all paths.")
