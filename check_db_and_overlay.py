import os
import requests
import boto3
from dotenv import load_dotenv

load_dotenv()

print("=" * 65)
print("🔍 1. DYNAMODB STATUS CHECK")
print("=" * 65)
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
table = dynamodb.Table('HarmonizedTrades')
res = table.scan()
items = res.get('Items', [])

active_count = 0
closed_count = 0

for item in items:
    status = item.get('exit_status')
    ticker = item.get('ticker')
    occ = item.get('occ_symbol')
    reason = item.get('exit_reason', item.get('exit_status'))
    ts = item.get('timestamp')
    if status == 'ACTIVE':
        active_count += 1
        print(f"  • [ACTIVE] {ticker} ({occ}) | Entry: ${item.get('entry_price')}")
    else:
        closed_count += 1
        print(f"  • [{status}] {ticker} ({occ}) | Reason: {reason} | Time: {ts}")

print(f"\nDynamoDB Summary: {active_count} Active | {closed_count} Closed")

print("\n" + "=" * 65)
print("🦅 2. TRADIER LIVE ACCOUNT POSITIONS CHECK")
print("=" * 65)
base_url = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
account_id = os.getenv("TRADIER_ACCOUNT_ID")

if token and account_id:
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        p_res = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers, timeout=5)
        if p_res.status_code == 200:
            pos_data = p_res.json().get('positions', {})
            pos_list = pos_data.get('position', []) if isinstance(pos_data, dict) else []
            if isinstance(pos_list, dict):
                pos_list = [pos_list]
            print(f"Live Tradier Open Positions Count: {len(pos_list)}")
            for p in pos_list:
                print(f"  • {p.get('symbol')} | Qty: {p.get('quantity')} | Cost Basis: ${p.get('cost_basis')}")
    except Exception as e:
        print(f"Tradier Error: {e}")

print("=" * 65)
