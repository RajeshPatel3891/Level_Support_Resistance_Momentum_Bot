#!/usr/bin/env python3
"""
HARM.AI // TELEMETRY DB RECORD INJECTOR
===============================================================================
Injects new telemetry trade records into harm_telemetry.db without corrupting
binary SQLite headers or losing existing schema columns/features.
"""

import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harm_telemetry.db')

def ensure_columns(cursor):
    """Ensures schema has execution_tag and auxiliary exit columns."""
    cursor.execute("PRAGMA table_info(trades)")
    existing_cols = [col[1] for col in cursor.fetchall()]
    
    new_cols = {
        'execution_tag': "TEXT DEFAULT 'SCJ'",
        'peak_price': "REAL DEFAULT 0.0",
        'is_runner': "INTEGER DEFAULT 0",
        'partial_pnl': "REAL DEFAULT 0.0",
        'min_pnl_seen': "REAL DEFAULT 0.0",
        'exit_timestamp': "TEXT"
    }

    for col_name, col_type in new_cols.items():
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}")
                print(f"[✓ SCHEMA] Added column: {col_name}")
            except sqlite3.OperationalError:
                pass

def insert_telemetry_record():
    if not os.path.exists(DB_PATH):
        print(f"[!] Target SQLite database {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Ensure schema is up to date
    ensure_columns(cursor)

    # Payload definition
    record = {
        "tenant_id": "COMPANY_A",
        "trade_id": "trade_f_call_01",
        "ticker": "F",
        "execution_tag": "SCJ",
        "strategy": "SMART_CSO_SCALP",
        "direction": "CALL",
        "spot_price": 12.50,
        "entry_price": 1.90,
        "shares": 1.0,
        "exit_status": "ACTIVE",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "occ_symbol": "F260904C00012000",
        "execution_env": "SANDBOX"
    }

    # Deduplication check
    cursor.execute("SELECT COUNT(*) FROM trades WHERE trade_id = ?", (record["trade_id"],))
    if cursor.fetchone()[0] > 0:
        print(f"[🛡️ DUP GUARD] Trade ID {record['trade_id']} already exists in harm_telemetry.db. Updating status...")
        cursor.execute("""
            UPDATE trades 
            SET execution_tag = ?, strategy = ?, entry_price = ?, exit_status = ?
            WHERE trade_id = ?
        """, (record["execution_tag"], record["strategy"], record["entry_price"], record["exit_status"], record["trade_id"]))
    else:
        cursor.execute("""
            INSERT INTO trades (
                tenant_id, trade_id, ticker, execution_tag, strategy, direction,
                spot_price, entry_price, shares, exit_status, timestamp, occ_symbol, execution_env
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record["tenant_id"], record["trade_id"], record["ticker"], record["execution_tag"],
            record["strategy"], record["direction"], record["spot_price"], record["entry_price"],
            record["shares"], record["exit_status"], record["timestamp"], record["occ_symbol"],
            record["execution_env"]
        ))
        print(f"[✓ SUCCESS] Injected record {record['trade_id']} ({record['ticker']} {record['execution_tag']}) into harm_telemetry.db")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    insert_telemetry_record()
