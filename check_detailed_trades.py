import boto3, os
from dotenv import load_dotenv

load_dotenv()
dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
table = dynamodb.Table('HarmonizedTrades')

res = table.scan()
items = res.get('Items', [])

active = [i for i in items if str(i.get('exit_status', '')).upper() == 'ACTIVE']
closed = [i for i in items if str(i.get('exit_status', '')).upper() != 'ACTIVE']

print("\n" + "="*85)
print(f" 📊 HARMONIZED PORTFOLIO DEEP-DIVE (GSG / MTTP / CSO ANALYTICS)")
print("="*85)
print(f" 🟢 Active Trades: {len(active)}   |   🔴 Closed Trades: {len(closed)}")
print("="*85)

print("\n[ ACTIVE POSITIONS // GSG & MTTP PARINGS ]")
if not active:
    print("  (No active positions found)")
for t in active:
    ticker = t.get('ticker', 'N/A')
    entry = float(t.get('entry_price', 0))
    mark = float(t.get('current_mark', 0))
    min_pnl = t.get('min_pnl_seen', 'N/A')
    gsg = t.get('gsg_status', 'N/A')
    mttp = t.get('mttp_status', 'N/A')
    strategy = t.get('strategy', 'N/A')
    ts = t.get('timestamp') or t.get('created_at', 'N/A')
    
    print(f"  • {ticker:<5} | Entry: ${entry:<5.2f} | Mark: ${mark:<5.2f} | Min PnL: {str(min_pnl):<5} | GSG: {gsg:<10} | MTTP: {mttp:<10} | Strat: {strategy}")

print("\n[ CLOSED POSITIONS // CSO REASONING & EXIT METRICS ]")
if not closed:
    print("  (No closed positions found)")
for t in closed:
    ticker = t.get('ticker', 'N/A')
    entry = float(t.get('entry_price', 0))
    exit_val = float(t.get('exit_price', 0))
    net_pnl = t.get('net_pnl', 'N/A')
    status = t.get('exit_status', 'N/A')
    cso_rec = t.get('cso_recommendation', 'N/A')
    cso_status = t.get('cso_status', 'N/A')
    gsg = t.get('gsg_status', 'N/A')
    mttp = t.get('mttp_status', 'N/A')
    
    diff = exit_val - entry
    pnl_pct = (diff / entry) * 100 if entry > 0 else 0
    
    print(f"  • {ticker:<5} | Entry: ${entry:<5.2f} | Exit: ${exit_val:<5.2f} | PnL: ${diff:<5.2f} ({pnl_pct:>+.1f}%) | Net: {net_pnl:<5} | Status: {status}")
    print(f"    └─> CSO Rec: {cso_rec} | CSO Status: {cso_status} | GSG: {gsg} | MTTP: {mttp}")

print("="*85 + "\n")
