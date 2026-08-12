import boto3
import os
import requests
import sqlite3
from dotenv import load_dotenv

load_dotenv()

dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
table = dynamodb.Table('HarmonizedTrades')

token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN')
headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

def to_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

# 1. Query all ACTIVE trades in DynamoDB
from boto3.dynamodb.conditions import Attr
res = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
items = res.get('Items', [])

print(f"[*] Found {len(items)} active positions to liquidate...")

total_realized_session = 0.0

for item in items:
    trade_id = item['trade_id']
    tenant_id = item['tenant_id']
    ticker = str(item.get('ticker', 'UNKNOWN'))
    occ_sym = str(item.get('occ_symbol', ticker))
    entry_p = to_float(item.get('entry_price') or item.get('cost'))
    shares = abs(to_float(item.get('shares'), 1.0))
    
    # Query live mark/bid price from Tradier API
    exit_p = entry_p
    url = f'https://sandbox.tradier.com/v1/markets/quotes?symbols={occ_sym}'
    try:
        r = requests.get(url, headers=headers, timeout=3)
        if r.status_code == 200:
            q = r.json().get('quotes', {}).get('quote', {})
            if isinstance(q, list) and len(q) > 0:
                q = q[0]
            bid = to_float(q.get('bid'))
            last = to_float(q.get('last'))
            if bid > 0:
                exit_p = bid
            elif last > 0:
                exit_p = last
    except Exception as e:
        print(f"[!] Quote error for {ticker}: {e}")

    pnl = round((exit_p - entry_p) * shares * 100.0, 2)
    total_realized_session += pnl

    # Update DynamoDB record
    table.update_item(
        Key={'tenant_id': tenant_id, 'trade_id': trade_id},
        UpdateExpression='SET exit_status = :status, exit_price = :ex, net_pnl = :pnl',
        ExpressionAttributeValues={
            ':status': 'FORCE_CLOSE',
            ':ex': str(round(exit_p, 2)),
            ':pnl': str(round(pnl, 2))
        }
    )
    print(f'[✓] Liquidated {ticker} ({occ_sym}): Entry ${entry_p:.2f} -> Exit ${exit_p:.2f} | Realized PnL: ${pnl:+.2f}')

# 2. Sync local SQLite DB if present
db_path = 'harm_telemetry.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("UPDATE trades SET exit_status = 'FORCE_CLOSE' WHERE exit_status = 'ACTIVE'")
    conn.commit()
    conn.close()
    print('[✓] Synchronized local SQLite telemetry state.')

print(f"\n[🎯 SUMMARY] All active trades closed. Net PnL of this liquidation: ${total_realized_session:+.2f}")
