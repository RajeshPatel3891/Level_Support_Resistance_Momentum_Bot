import re

with open("run_gex_monitor.py", "r") as f:
    code = f.read()

# Upgraded position fetcher pointing directly to DynamoDB
new_fetcher = """def fetch_active_trades():
    import boto3, os
    from boto3.dynamodb.conditions import Attr
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        res = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        parsed = []
        for item in res.get('Items', []):
            entry_p = float(item.get('entry_price', 0.0))
            parsed.append({
                'id': str(item.get('trade_id')),
                'ticker': str(item.get('ticker')),
                'entry_price': entry_p,
                'stop_loss': float(item.get('stop_loss', round(entry_p * 0.80, 2))),
                'take_profit': float(item.get('take_profit', round(entry_p * 1.50, 2))),
                'strategy': str(item.get('strategy', 'BREAKOUT')),
                'direction': str(item.get('direction', 'CALL')),
                'occ_symbol': str(item.get('occ_symbol', item.get('ticker'))),
                'shares': abs(float(item.get('shares', 1.0))),
                'tenant_id': str(item.get('tenant_id', 'COMPANY_A')),
                'gsg_status': 'ARMED',
                'mttp_status': 'ACTIVE_45M_GUARD'
            })
        return parsed
    except Exception as e:
        print(f"[-] DynamoDB Fetch Error in GEX Monitor: {e}")
        return []"""

if "def fetch_active_trades" in code:
    pattern = r"def fetch_active_trades\(.*?\):.+?return\s+.*?\n"
    code = re.sub(pattern, new_fetcher + "\n", code, flags=re.DOTALL)
    with open("run_gex_monitor.py", "w") as f:
        f.write(code)
    print("[✓] Successfully patched run_gex_monitor.py to pull active positions directly from DynamoDB!")
