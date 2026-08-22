#!/usr/bin/env python3
import os
import boto3
from dotenv import load_dotenv
import src.gex_exit_monitor as gex

if os.path.exists('.env.prod'):
    load_dotenv('.env.prod', override=True)
else:
    load_dotenv(override=True)

dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
table = dynamodb.Table('HarmonizedTrades')

res = table.scan()
items = res.get('Items', [])

KNOWN_FILLS = {
    'SNAP260821P00005500': {'entry': 0.30, 'exit': 0.28},
    'SOFI260821P00019000': {'entry': 0.18, 'exit': 0.20}
}

for item in items:
    ticker = item.get('ticker')
    occ_symbol = item.get('occ_symbol')
    t_id = item.get('trade_id')
    item_tenant = item.get('tenant_id')
    
    if ticker in ['SNAP', 'SOFI'] and item.get('exit_status') == 'GHOST_RECONCILED_CLOSED':
        entry_px = KNOWN_FILLS.get(occ_symbol, {}).get('entry', 0.0)
        actual_exit_px = KNOWN_FILLS.get(occ_symbol, {}).get('exit', 0.0)
        shares = 1.0
        realized_pnl = round((actual_exit_px - entry_px) * shares * 100.0, 2)
        
        print(f"[✓ REPAIR SUCCESS] {ticker} ({occ_symbol}) | Tenant: {item_tenant} | Entry: {entry_px:.2f} | Actual Fill: {actual_exit_px:.2f} | PnL: {realized_pnl:+.2f}")
        
        table.update_item(
            Key={'tenant_id': item_tenant, 'trade_id': t_id},
            UpdateExpression='SET entry_price = :ep, exit_price = :px, net_pnl = :pnl',
            ExpressionAttributeValues={
                ':ep': str(entry_px),
                ':px': str(actual_exit_px),
                ':pnl': str(realized_pnl)
            }
        )
        gex.sync_local_sqlite_exit(t_id, ticker, 'GHOST_RECONCILED_CLOSED', actual_exit_px, item.get('exit_timestamp', ''), realized_pnl, remaining_shares=0)

