import boto3, os
from dotenv import load_dotenv

load_dotenv()
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
table = dynamodb.Table('HarmonizedTrades')

res = table.scan()
items = res.get('Items', [])

closed = [i for i in items if str(i.get('exit_status', '')).upper() != 'ACTIVE']

print(f"\n=== INSPECTING CLOSED TRADE KEYS & COMPUTING PNL ===")
for t in closed:
    print(f"\nRaw DynamoDB Keys for {t.get('ticker')}:", list(t.keys()))
    
    ticker = t.get('ticker')
    entry = float(t.get('entry_price', 0))
    exit_val = float(t.get('exit_price', 0))
    status = t.get('exit_status')
    
    # Calculate PnL percentage or dollar difference
    diff = exit_val - entry
    pnl_pct = (diff / entry) * 100 if entry > 0 else 0
    
    print(f"   -> Ticker: {ticker} | Entry: ${entry:.2f} | Exit: ${exit_val:.2f} | Calculated Diff: ${diff:.2f} ({pnl_pct:.2f}%) | Status: {status}")

