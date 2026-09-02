import os, requests, boto3
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr

load_dotenv('.env.prod', override=True)

TOKEN = os.getenv("TRADIER_TOKEN")
ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "6YB87601")
BASE_URL = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip('/')
REGION = os.getenv("AWS_REGION", "us-east-1")

headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
res = requests.get(f"{BASE_URL}/accounts/{ACCOUNT_ID}/positions", headers=headers, timeout=5)

live_symbols = set()
if res.status_code == 200:
    data = res.json().get("positions", {})
    if isinstance(data, dict):
        pos_list = data.get("position", [])
        if isinstance(pos_list, dict):
            pos_list = [pos_list]
        live_symbols = {p.get("symbol") for p in pos_list if p.get("symbol")}

print(f"[✓] Tradier Active Contracts: {live_symbols}")

dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table('HarmonizedTrades')

response = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
active_items = response.get('Items', [])

seen = set()
for item in active_items:
    tenant_id = item.get('tenant_id', 'COMPANY_A_PROD')
    trade_id = item.get('trade_id')
    occ = item.get('occ_symbol', item.get('ticker'))
    
    if occ not in live_symbols:
        print(f"[🗑️ CLOSING GHOST] {occ} ({trade_id}) not open on Tradier.")
        table.update_item(
            Key={'tenant_id': tenant_id, 'trade_id': trade_id},
            UpdateExpression='SET exit_status = :st, shares = :sh',
            ExpressionAttributeValues={':st': 'GHOST_RECONCILED_CLOSED', ':sh': '0'}
        )
    elif occ in seen:
        print(f"[🗑️ REMOVING DUPLICATE] {occ} ({trade_id})")
        table.update_item(
            Key={'tenant_id': tenant_id, 'trade_id': trade_id},
            UpdateExpression='SET exit_status = :st, shares = :sh',
            ExpressionAttributeValues={':st': 'DUPLICATE_PURGED', ':sh': '0'}
        )
    else:
        seen.add(occ)
        print(f"[✓ ACTIVE MATCH] {occ} verified open.")

print("[✓] DynamoDB reconciliation complete.")
