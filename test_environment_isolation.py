#!/usr/bin/env python3
"""
HARM.AI // UNIT TEST: DYNAMIC ENVIRONMENT ISOLATION
===============================================================================
Verifies schema tagging (EXECUTION_ENV & IS_LIVE) and query filtering across
SQLite, DynamoDB, and dashboard_server fetch functions.
"""

import os
import sys
import sqlite3
import boto3
from boto3.dynamodb.conditions import Attr

# Import functions from dashboard_server
import dashboard_server

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harm_telemetry.db')

def setup_mock_records():
    print("----------------------------------------------------------")
    print("[1] Injecting Mock Tagged Trades into SQLite & DynamoDB...")
    
    # 1. Ingest into SQLite
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("PRAGMA table_info(trades)")
    cols = [col[1] for col in c.fetchall()]
    if 'execution_env' not in cols:
        c.execute("ALTER TABLE trades ADD COLUMN execution_env TEXT DEFAULT 'SANDBOX'")
        
    c.execute("""
        INSERT INTO trades (
            ticker, timestamp, strategy, direction, spot_price, entry_price, 
            exit_status, stop_loss, take_profit, shares, occ_symbol, is_live, execution_env
        ) VALUES 
        ('TEST_PROD', '2026-08-13 21:00:00', 'UNIT_TEST', 'CALL', 10.0, 1.0, 'ACTIVE', 0.8, 1.5, 1, 'TEST_PROD_OCC', 1, 'PRODUCTION'),
        ('TEST_SAND', '2026-08-13 21:00:00', 'UNIT_TEST', 'PUT', 10.0, 1.0, 'ACTIVE', 0.8, 1.5, 1, 'TEST_SAND_OCC', 0, 'SANDBOX')
    """)
    conn.commit()
    conn.close()

    # 2. Ingest into DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    table = dynamodb.Table('HarmonizedTrades')
    
    table.put_item(Item={
        'tenant_id': 'COMPANY_A',
        'trade_id': 'TEST_PROD_999',
        'ticker': 'TEST_PROD',
        'timestamp': '2026-08-13 21:00:00',
        'strategy': 'UNIT_TEST',
        'direction': 'CALL',
        'spot_price': '10.00',
        'entry_price': '1.00',
        'shares': '1.0',
        'stop_loss': '0.80',
        'take_profit': '1.50',
        'net_pnl': '0.0',
        'exit_status': 'ACTIVE',
        'is_live': 1,
        'execution_env': 'PRODUCTION'
    })
    
    table.put_item(Item={
        'tenant_id': 'COMPANY_A',
        'trade_id': 'TEST_SAND_999',
        'ticker': 'TEST_SAND',
        'timestamp': '2026-08-13 21:00:00',
        'strategy': 'UNIT_TEST',
        'direction': 'PUT',
        'spot_price': '10.00',
        'entry_price': '1.00',
        'shares': '1.0',
        'stop_loss': '0.80',
        'take_profit': '1.50',
        'net_pnl': '0.0',
        'exit_status': 'ACTIVE',
        'is_live': 0,
        'execution_env': 'SANDBOX'
    })
    print("[✓] Injected PROD and SANDBOX mock positions cleanly.")

def test_production_filter():
    print("----------------------------------------------------------")
    print("[2] Testing PRODUCTION Environment Query Isolation...")
    dashboard_server.CURRENT_ENV = "PRODUCTION"
    dashboard_server.TARGET_IS_LIVE = 1
    
    active_trades = dashboard_server.fetch_all_active_dynamo_positions()
    tickers = [t['ticker'] for t in active_trades]
    
    print(f"[*] Fetched Active Tickers in PROD mode: {tickers}")
    assert 'TEST_PROD' in tickers, "FAILED: Production record was not returned in PROD mode!"
    assert 'TEST_SAND' not in tickers, "FAILED: Sandbox record leaked into PROD mode query!"
    print("[✓] PASS: Production mode strictly isolated Production data.")

def test_sandbox_filter():
    print("----------------------------------------------------------")
    print("[3] Testing SANDBOX Environment Query Isolation...")
    dashboard_server.CURRENT_ENV = "SANDBOX"
    dashboard_server.TARGET_IS_LIVE = 0
    
    active_trades = dashboard_server.fetch_all_active_dynamo_positions()
    tickers = [t['ticker'] for t in active_trades]
    
    print(f"[*] Fetched Active Tickers in SANDBOX mode: {tickers}")
    assert 'TEST_SAND' in tickers, "FAILED: Sandbox record was not returned in SANDBOX mode!"
    assert 'TEST_PROD' not in tickers, "FAILED: Production record leaked into SANDBOX mode query!"
    print("[✓] PASS: Sandbox mode strictly isolated Sandbox data.")

def teardown_mock_records():
    print("----------------------------------------------------------")
    print("[4] Cleaning Up Test Artifacts from SQLite & DynamoDB...")
    
    # 1. Clean SQLite
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM trades WHERE ticker IN ('TEST_PROD', 'TEST_SAND')")
    conn.commit()
    conn.close()

    # 2. Clean DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    table = dynamodb.Table('HarmonizedTrades')
    table.delete_item(Key={'tenant_id': 'COMPANY_A', 'trade_id': 'TEST_PROD_999'})
    table.delete_item(Key={'tenant_id': 'COMPANY_A', 'trade_id': 'TEST_SAND_999'})
    print("[✓] Teardown complete. Databases purged of test records.")

if __name__ == '__main__':
    try:
        setup_mock_records()
        test_production_filter()
        test_sandbox_filter()
        print("==========================================================")
        print("🎉 ALL ENVIRONMENT ISOLATION UNIT TESTS PASSED!")
        print("==========================================================")
    except Exception as e:
        print(f"\n❌ UNIT TEST FAILED: {e}")
    finally:
        teardown_mock_records()
