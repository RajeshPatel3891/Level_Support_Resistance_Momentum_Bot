import boto3, os
from dotenv import load_dotenv

load_dotenv()
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
table = dynamodb.Table('HarmonizedTrades')

res = table.scan()
items = res.get('Items', [])

active = [i for i in items if str(i.get('exit_status', '')).upper() == 'ACTIVE']
closed = [i for i in items if str(i.get('exit_status', '')).upper() != 'ACTIVE']

print("\n" + "="*70)
print(f" 📊 HARMONIZED TRADING PORTFOLIO STATE (Total Items: {len(items)})")
print("="*70)
print(f" 🟢 Active Trades: {len(active)}   |   🔴 Closed Trades: {len(closed)}")
print("="*70)

print("\n[ ACTIVE POSITIONS ]")
if not active:
    print("  (No active positions found)")
for t in active:
    ticker = t.get('ticker', 'N/A')
    entry = float(t.get('entry_price', 0))
    mark = float(t.get('current_mark', 0))
    min_pnl = t.get('min_pnl_seen', 'N/A')
    status = t.get('exit_status', 'N/A')
    ts = t.get('timestamp') or t.get('created_at', 'N/A')
    
    print(f"  • Ticker: {ticker:<5} | Entry: ${entry:<6.2f} | Mark: ${mark:<6.2f} | Min PnL Seen: {min_pnl:<6} | Status: {status} | Time: {ts}")

print("\n[ CLOSED POSITIONS ]")
if not closed:
    print("  (No closed positions found)")
for t in closed:
    ticker = t.get('ticker', 'N/A')
    entry = float(t.get('entry_price', 0))
    exit_val = float(t.get('exit_price', 0))
    net_pnl = t.get('net_pnl', 'N/A')
    status = t.get('exit_status', 'N/A')
    ts = t.get('timestamp') or t.get('created_at', 'N/A')
    
    diff = exit_val - entry
    pnl_pct = (diff / entry) * 100 if entry > 0 else 0
    
    print(f"  • Ticker: {ticker:<5} | Entry: ${entry:<6.2f} | Exit: ${exit_val:<6.2f} | Diff: ${diff:<6.2f} ({pnl_pct:>+.2f}%) | Net PnL: {net_pnl} | Status: {status}")

print("="*70 + "\n")
