import boto3
from datetime import datetime

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
trades_table = dynamodb.Table('HarmonizedTrades')

tickers = ["AAPL", "TSLA", "NVDA", "PLTR", "RIVN", "SOFI", "INTC", "AAL", "F"]

print("🚀 Injecting active simulated trades directly into DynamoDB (HarmonizedTrades)...")

for idx, ticker in enumerate(tickers):
    trade_id = str(9000 + idx)
    item = {
        'tenant_id': 'COMPANY_A',
        'trade_id': trade_id,
        'ticker': ticker,
        'direction': 'CALL',
        'status': 'ACTIVE',
        'exit_status': 'ACTIVE',
        'shares': '10',
        'entry_price': '0.58',
        'cost': '580.00',
        'spot_price': '100.00',
        'opened_at': datetime.now().isoformat()
    }
    trades_table.put_item(Item=item)
    print(f"  [✓] Injected active CALL trade for {ticker} (Trade ID: {trade_id})")

print("\n[✓] Direct DynamoDB batch injection complete!")
