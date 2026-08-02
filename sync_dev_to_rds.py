import sqlite3
import pandas as pd
from sqlalchemy import create_engine
import io

db_target = 'harmbot-prod-db.c10wwys0a2ut.us-east-1.rds.amazonaws.com'
pg_engine = create_engine(
    f'postgresql://postgres:Postgressisscalable$5^@{db_target}:5432/postgres'
)

conn = sqlite3.connect('harm_telemetry.db')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [r[0] for r in cursor.fetchall()]

def psql_insert_copy(table, conn, keys, data_iter):
    dbapi_conn = conn.connection
    with dbapi_conn.cursor() as cur:
        s_buf = io.StringIO()
        for row in data_iter:
            s_buf.write('\t'.join([str(x) if x is not None else '' for x in row]) + '\n')
        s_buf.seek(0)
        columns = ', '.join([f'"{k}"' for k in keys])
        table_name = f'"{table.name}"'
        sql = f"COPY {table_name} ({columns}) FROM STDIN WITH (FORMAT csv, DELIMITER '\t', NULL '')"
        cur.copy_expert(sql=sql, file=s_buf)

print("--- SYNCING DEV TELEMETRY DIRECTLY TO RDS ---")
for table in tables:
    df = pd.read_sql_query(f'SELECT * FROM {table}', conn)
    print(f"Syncing {len(df):,} rows from Dev table '{table}' -> RDS PostgreSQL...")
    try:
        use_method = psql_insert_copy if len(df) > 10000 else None
        df.to_sql(
            table, 
            pg_engine, 
            if_exists='replace', 
            index=False, 
            chunksize=50000 if len(df) > 10000 else 5000, 
            method=use_method
        )
        print(f"[✓] Successfully updated '{table}' in RDS!\n")
    except Exception as e:
        print(f"[!] Failed to sync '{table}'. Error: {e}\n")

conn.close()
print("--- ALL DEV TELEMETRY MIGRATED TO RDS ---")
