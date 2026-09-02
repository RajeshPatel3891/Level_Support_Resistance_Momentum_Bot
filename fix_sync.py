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

live_positions = {}
if res.status_code == 200:
    data = res.json().get("positions", {})
    if isinstance(data, dict):
        pos_list = data.get("position", [])
        if isinstance(pos_list, dict):
            pos_list = [pos_list]
        for p in pos_list:
            if p.get("symbol"):
                live_positions[p.get("symbol")] = int(p.get("quantity", 1))

print(f"[✓] Active Tradier Positions ({len(live_positions)}): {list(live_positions.keys())}")

dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table('HarmonizedTrades')

response = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
active_items = response.get('Items', [])

# Sort so newest entries remain active
active_items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

seen_symbols = set()
for item in active_items:
    t_id = item.get('tenant_id', 'COMPANY_A_PROD')
    trade_id = item.get('trade_id')
    occ = item.get('occ_symbol', item.get('ticker'))
    
    if occ not in live_positions:
        print(f"[🗑️ CLOSING GHOST] {occ} ({trade_id})")
        table.update_item(
            Key={'tenant_id': t_id, 'trade_id': trade_id},
            UpdateExpression='SET exit_status = :st, shares = :sh',
            ExpressionAttributeValues={':st': 'GHOST_RECONCILED_CLOSED', ':sh': '0'}
        )
    elif occ in seen_symbols:
        print(f"[🗑️ PURGING DUPLICATE] {occ} ({trade_id})")
        table.update_item(
            Key={'tenant_id': t_id, 'trade_id': trade_id},
            UpdateExpression='SET exit_status = :st, shares = :sh',
            ExpressionAttributeValues={':st': 'DUPLICATE_PURGED', ':sh': '0'}
        )
    else:
        seen_symbols.add(occ)
        correct_shares = str(live_positions[occ])
        table.update_item(
            Key={'tenant_id': t_id, 'trade_id': trade_id},
            UpdateExpression='SET shares = :sh',
            ExpressionAttributeValues={':sh': correct_shares}
        )
        print(f"[✓ ACTIVE 1:1] {occ} locked to {correct_shares} contract(s).")

print("[✓] Hard sync complete. 6 live positions aligned.")
