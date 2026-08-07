import sqlite3

def run_preboot_migration():
    for db_file in ["harmonized_trading.db", "harm_telemetry.db"]:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                timestamp TEXT,
                strategy TEXT,
                direction TEXT,
                spot_price REAL DEFAULT 0.0,
                exit_price REAL DEFAULT 0.0,
                exit_status TEXT DEFAULT 'OPEN',
                net_pnl REAL DEFAULT 0.0,
                execution_origin TEXT DEFAULT 'LEGACY',
                take_profit REAL DEFAULT 0.0,
                stop_loss REAL DEFAULT 0.0,
                shares REAL DEFAULT 0.0,
                cost REAL DEFAULT 0.0,
                occ_symbol TEXT
            );
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gex_telemetry (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                spot_price REAL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        for col, ctype in [
            ("take_profit", "REAL DEFAULT 0.0"), 
            ("stop_loss", "REAL DEFAULT 0.0"), 
            ("shares", "REAL DEFAULT 0.0"), 
            ("cost", "REAL DEFAULT 0.0"), 
            ("occ_symbol", "TEXT"), 
            ("exit_status", "TEXT DEFAULT 'OPEN'"), 
            ("spot_price", "REAL DEFAULT 0.0")
        ]:
            try:
                cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {ctype};")
            except Exception:
                pass
        conn.commit()
        conn.close()
    print("[✓] Pre-boot SQLite databases fully verified and migrated!")

if __name__ == "__main__":
    run_preboot_migration()
