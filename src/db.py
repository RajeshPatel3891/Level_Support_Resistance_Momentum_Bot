import sqlite3
from schema_manifest import TABLE_SCHEMAS, COLUMN_TYPES

def get_db(db_path="harm_telemetry.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Enable WAL Mode for concurrent multi-process reads/writes
    cursor.execute("PRAGMA journal_mode=WAL;")
    
    # Enforce Schema Manifest on every connect
    for table_name, create_sql in TABLE_SCHEMAS.items():
        cursor.execute(create_sql)
        
    for table_name, cols_map in COLUMN_TYPES.items():
        existing = [row[1] for row in cursor.execute(f"PRAGMA table_info({table_name});")]
        for col_name, col_def in cols_map.items():
            if col_name not in existing:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def};")
                
    conn.commit()
    return conn
