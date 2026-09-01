#!/usr/bin/env python3
"""
HARM.AI // LIVE GEX EXIT MONITOR DUAL-DB TEST INJECTOR
===============================================================================
Injects a mock ACTIVE position into both harm_telemetry.db and DynamoDB so that
src/gex_exit_monitor.py can detect and monitor it live.
"""

import sqlite3
import boto3
import os
from datetime import datetime

DB_PATH = "harm_telemetry.db"
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

def run_pipeline_test():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Inject into local SQLite
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE trade_id = 'STREAM_TEST_NVDA'")
    cursor.execute("""
        INSERT INTO trades (
            tenant_id, trade_id, ticker, execution_tag, strategy, direction,
            spot_price, entry_price, shares, exit_status, timestamp, occ_symbol, execution_env
        ) VALUES ('COMPANY_A', 'STREAM_TEST_NVDA', 'NVDA', 'SCJ', 'SMART_CSO_SCALP', 'CALL', 235.00, 2.00, 1.0, 'ACTIVE', ?, 'NVDA260904C00235000', 'SANDBOX')
    """, (now_str,))
    conn.commit()
    conn.close()

    # 2. Inject into AWS DynamoDB
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
        table.put_item(Item={
            'tenant_id': 'COMPANY_A',
            'trade_id': 'STREAM_TEST_NVDA',
            'ticker': 'NVDA',
            'occ_symbol': 'NVDA260904C00235000',
            'execution_tag': 'SCJ',
            'strategy': 'SMART_CSO_SCALP',
            'direction': 'CALL',
            'entry_price': '2.00',
            'spot_price': '235.00',
            'shares': '1',
            'exit_status': 'ACTIVE',
            'timestamp': now_str,
            'peak_price': '2.00',
            'stop_loss': '1.60'
        })
        print("[✓ DYNAMODB] Injected STREAM_TEST_NVDA into HarmonizedTrades table.")
    except Exception as e:
        print(f"[!] DynamoDB Injection Note: {e}")

    print("=" * 80)
    print("🚀 Injected STREAM_TEST_NVDA ($2.00 entry) into SQLite & DynamoDB")
    print("   Run 'python3 src/gex_exit_monitor.py' to watch it evaluate live!")
    print("=" * 80)

if __name__ == "__main__":
    run_pipeline_test()
