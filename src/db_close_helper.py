#!/usr/bin/env python3
"""
HARM.AI // UNIFIED DB CLOSE HELPER
===============================================================================
Instantly transitions trades from ACTIVE -> CLOSED across both SQLite and AWS DynamoDB.
Frees up ticker slots immediately while preserving historical PnL and exit prices.
"""

import os
import sqlite3
import boto3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'harm_telemetry.db')
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

def close_active_trade(ticker, exit_reason="CSO_SCALP_EXIT", fill_price=0.0, net_pnl=0.0):
    """
    Forces trade status to CLOSED in SQLite and DynamoDB.
    Unlocks check_active_position_exists() for immediate re-entry without overwriting historical data.
    """
    ticker = ticker.upper()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Update SQLite
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                UPDATE trades 
                SET exit_status = 'CLOSED', 
                    cso_status = ?, 
                    exit_price = CASE WHEN ? > 0 THEN ? ELSE exit_price END, 
                    net_pnl = CASE WHEN ? != 0.0 THEN ? ELSE net_pnl END, 
                    exit_timestamp = ?
                WHERE UPPER(ticker) = ? AND (UPPER(exit_status) = 'ACTIVE' OR UPPER(exit_status) LIKE '%TRIGGERED%')
            """, (exit_reason, float(fill_price), float(fill_price), float(net_pnl), float(net_pnl), now_str, ticker))
            conn.commit()
            conn.close()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [DB_CLOSE] [✓ SQLite] Closed active slot for {ticker} (Preserved PnL/Price).")
    except Exception as e:
        print(f"[!] SQLite close_active_trade error ({ticker}): {e}")

    # 2. Update DynamoDB
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
        res = table.scan(
            FilterExpression="ticker = :t AND (exit_status = :act OR contains(exit_status, :trig))",
            ExpressionAttributeValues={":t": ticker, ":act": "ACTIVE", ":trig": "TRIGGERED"}
        )
        for item in res.get('Items', []):
            up_expr = "SET exit_status = :cls, #st = :cls, cso_status = :r"
            attr_vals = {':cls': 'CLOSED', ':r': exit_reason}
            
            if fill_price > 0:
                up_expr += ", exit_price = :px"
                attr_vals[':px'] = str(fill_price)
            if net_pnl != 0.0:
                up_expr += ", net_pnl = :pnl"
                attr_vals[':pnl'] = str(net_pnl)

            table.update_item(
                Key={'tenant_id': item.get('tenant_id', 'COMPANY_A'), 'trade_id': item['trade_id']},
                UpdateExpression=up_expr,
                ExpressionAttributeNames={'#st': 'status'},
                ExpressionAttributeValues=attr_vals
            )
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [DB_CLOSE] [✓ DynamoDB] Synchronized CLOSED status for {ticker}.")
    except Exception as e:
        print(f"[!] DynamoDB close_active_trade error ({ticker}): {e}")

if __name__ == "__main__":
    import sys
    t_target = sys.argv[1] if len(sys.argv) > 1 else "SOFI"
    close_active_trade(t_target, exit_reason="MANUAL_CLEANUP", fill_price=0.0, net_pnl=0.0)
