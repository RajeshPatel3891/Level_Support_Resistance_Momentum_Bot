import sqlite3
from schema_manifest import TABLE_SCHEMAS

def rebuild():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    print("================================================================================")
    print(" HARM.AI // DATABASE SCHEMA UNIFICATION & ALIGNMENT ")
    print("================================================================================")
    
    for table_name, ddl in TABLE_SCHEMAS.items():
        cursor.execute(f"DROP TABLE IF EXISTS {table_name};")
        cursor.execute(ddl)
        print(f"[✓] Unified Schema table '{table_name}' initialized successfully.")
        
    print("[*] Seeding production ledger details...")
    cursor.execute("""
        INSERT INTO account_ledger 
        (balance, available_cash, starting_settled_cash, settled_cash, available_settled_cash, unsettled_cash, deployed_capital, net_pnl, realized_pnl, unrealized_pnl) 
        VALUES (10000.0, 10000.0, 10000.0, 10000.0, 10000.0, 0.0, 0.0, 0.0, 0.0, 0.0);
    """)
    
    conn.commit()
    conn.close()
    print("[✓] SQLite database successfully rebuilt from schema_manifest.py.")

if __name__ == "__main__":
    rebuild()
