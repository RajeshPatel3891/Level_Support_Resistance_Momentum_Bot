import boto3, os
from dotenv import load_dotenv

load_dotenv()
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
table = dynamodb.Table('HarmonizedTrades')

res = table.scan()
items = res.get('Items', [])

active = [i for i in items if str(i.get('exit_status', '')).upper() == 'ACTIVE']
closed = [i for i in items if str(i.get('exit_status', '')).upper() != 'ACTIVE']

print(f"\n================ DYNAMODB SCAN RESULTS ================")
print(f"Total Table Items: {len(items)}")
print(f"Active Trades Count: {len(active)} | Closed Trades Count: {len(closed)}\n")

print("--- 🟢 ACTIVE TRADES ---")
for t in active:
    ticker = t.get('ticker')
    entry = t.get('entry_price')
    status = t.get('exit_status')
    ts = t.get('timestamp') or t.get('created_at')
    min_pnl = t.get('min_pnl_seen', 'N/A')
    print(f"Ticker: {ticker} | Entry: ${entry} | Min PnL Seen: {min_pnl} | Status: {status} | Timestamp: {ts}")

print("\n--- 🔴 CLOSED TRADES ---")
for t in closed:
    ticker = t.get('ticker')
    entry = t.get('entry_price')
    exit_price = t.get('exit_price', 'N/A')
    status = t.get('exit_status')
    ts = t.get('timestamp') or t.get('created_at')
    pnl = t.get('pnl', 'N/A')
    print(f"Ticker: {ticker} | Entry: ${entry} | Exit: ${exit_price} | PnL: {pnl} | Status: {status} | Timestamp: {ts}")

print("=======================================================")
