#!/usr/bin/env python3
"""
HARM.AI // FULL DYNAMIC STOP LADDER MATRIX TESTER (UPDATED SEEDING)
===============================================================================
Tests all 5 exit engine branches offline:
1. +5% Peak  -> Breakeven Floor (+1%)
2. +20% Peak -> Peak - 6% Lock ($2.28)
3. +35% Peak -> Peak - 8% Lock ($2.54)
4. Noise Filter vs Momentum Cut (Stock Level Breach Check)
5. Sub-$0.50 Low-Dollar Absolute Cushion ($0.10 Floor -> $0.30)
"""

import os
import sqlite3
import boto3
import src.gex_exit_monitor as gem

DB_PATH = "harm_telemetry.db"
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
os.environ["ACTIVE_TICKERS"] = "TEST5,TEST20,TEST35,TESTCUT,TESTLOW"

# Setup Mock Test Positions across all scenarios (seeded stop_loss = 0.0 to test engine logic)
test_items = [
    # (trade_id, ticker, occ, entry, spot, peak, target, live_option, live_spot, expected_label)
    ("T_5PCT",   "TEST5",  "TEST5_C",  2.00, 100.0, 2.12, 100.0, 2.12, 100.0, "+5% Breakeven Floor"),
    ("T_20PCT",  "TEST20", "TEST20_C", 2.00, 100.0, 2.40, 100.0, 2.38, 100.0, "+20% Dynamic Lock (Peak -6%)"),
    ("T_35PCT",  "TEST35", "TEST35_C", 2.00, 100.0, 2.70, 100.0, 2.65, 100.0, "+35% Dynamic Lock (Peak -8%)"),
    ("T_CUT",    "TESTCUT","TESTCUT_C",2.00, 100.0, 2.00, 100.0, 1.82, 99.0,  "Early Structural Cut (Stock Support Breached)"),
    ("T_LOW",    "TESTLOW","TESTLOW_C",0.40, 50.0,  0.40, 50.0,  0.38, 50.0,  "Sub-$0.50 Low Dollar Cushion ($0.10 Absolute)")
]

# Mock quote engine lookup table
mock_quotes = {item[2]: (item[7], "https://sandbox.tradier.com/v1") for item in test_items}
mock_gex = {
    "TEST5":   (100.0, 100.0, 0.0),
    "TEST20":  (100.0, 100.0, 0.0),
    "TEST35":  (100.0, 100.0, 0.0),
    "TESTCUT": (99.0,  100.0, 0.0), # Spot 99.0 < GEX Target 100.0 -> BREACHED!
    "TESTLOW": (50.0,  50.0,  0.0)
}

gem.get_live_quote = lambda symbol: mock_quotes.get(symbol, (0.0, ""))
gem.get_gex_target_info = lambda ticker: mock_gex.get(ticker, (0.0, 0.0, 0.0))

def run_suite():
    print("=" * 95)
    print("🧪 HARM.AI // FULL MULTI-BRANCH DYNAMIC STOP MATRIX EVALUATION")
    print("=" * 95)

    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    table = dynamodb.Table('HarmonizedTrades')

    # Seed DynamoDB with test items
    for t_id, ticker, occ, entry, spot, peak, target, live_opt, live_s, label in test_items:
        table.put_item(Item={
            'tenant_id': 'COMPANY_A',
            'trade_id': t_id,
            'ticker': ticker,
            'occ_symbol': occ,
            'execution_tag': 'SCJ',
            'strategy': 'SMART_CSO_SCALP',
            'direction': 'CALL',
            'entry_price': str(entry),
            'spot_price': str(spot),
            'shares': '1',
            'exit_status': 'ACTIVE',
            'timestamp': '2026-08-30 10:00:00',
            'peak_price': str(peak),
            'stop_loss': '0.0'
        })

    # Execute monitor pass
    gem.evaluate_gex_exits()

    # Clean up DynamoDB test records immediately
    for t_id, _, _, _, _, _, _, _, _, _ in test_items:
        table.delete_item(Key={'tenant_id': 'COMPANY_A', 'trade_id': t_id})

    print("=" * 95)
    print("🧹 [CLEANUP] Purged matrix test items from DynamoDB.")
    print("=" * 95)

if __name__ == "__main__":
    run_suite()
