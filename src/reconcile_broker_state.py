import requests
import sqlite3
import boto3
import os
import re

ACCOUNT_ID = '6YB87601'
TOKEN = 'fyR75AACwlIYhkMyev1doRh6gnSr'
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

def reconcile():
    print("=" * 70)
    print(" 🔄 HARM.AI // PRE-FLIGHT BROKER-TO-DATABASE RECONCILER")
    print("=" * 70)

    # 1. Fetch Ground Truth from Tradier API
    headers = {'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/json'}
    try:
        res = requests.get(f'https://api.tradier.com/v1/accounts/{ACCOUNT_ID}/positions', headers=headers)
        raw_positions = res.json().get('positions', {})
        
        if raw_positions == 'null' or not raw_positions:
            active_symbols = []
        else:
            pos_list = raw_positions.get('position', [])
            if isinstance(pos_list, dict): 
                pos_list = [pos_list]
            active_symbols = [p.get('symbol') for p in pos_list if int(p.get('quantity', 0)) != 0]
    except Exception as e:
        print(f"[-] Broker API Error during reconciliation: {e}")
        return

    print(f"[*] Tradier API Active Positions ({len(active_symbols)}): {active_symbols}")

    # 2. Reconcile Local SQLite
    conn = sqlite3.connect('harm_telemetry.db')
    cursor = conn.cursor()
    
    if not active_symbols:
        cursor.execute("UPDATE trades SET is_live = 0, exit_status = 'RECONCILED_CLOSED' WHERE is_live = 1;")
        print("[✓] SQLite reconciled: Marked ALL legacy records as closed.")
    conn.commit()
    conn.close()

    # 3. Reconcile DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    table = dynamodb.Table('HarmonizedTrades')
    items = table.scan().get('Items', [])

    cleared = 0
    for item in items:
        occ = item.get('occ_symbol') or item.get('ticker')
        if item.get('is_live') == 1 and occ not in active_symbols:
            table.update_item(
                Key={'tenant_id': item['tenant_id'], 'trade_id': item['trade_id']},
                UpdateExpression='SET exit_status = :status, is_live = :zero',
                ExpressionAttributeValues={':status': 'RECONCILED_CLOSED', ':zero': 0}
            )
            cleared += 1

    print(f"[✓] DynamoDB reconciled: Cleared {cleared} ghost records.")
    print("=" * 70)

if __name__ == '__main__':
    reconcile()
