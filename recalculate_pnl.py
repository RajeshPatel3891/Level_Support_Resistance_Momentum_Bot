import boto3
import os
import requests
from dotenv import load_dotenv

load_dotenv()

dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
table = dynamodb.Table('HarmonizedTrades')

token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN')
account_id = os.getenv('TRADIER_ACCOUNT_ID')
headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

def to_float(val, default=0.0):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

res = table.scan()
items = res.get('Items', [])

print(f"[*] Auditing {len(items)} total records in HarmonizedTrades...")

for item in items:
    exit_status = str(item.get('exit_status', ''))
    if exit_status not in ['CLOSED', 'FORCE_CLOSE']:
        continue

    trade_id = item['trade_id']
    tenant_id = item['tenant_id']
    ticker = str(item.get('ticker', 'UNKNOWN'))
    occ_sym = str(item.get('occ_symbol', ticker))
    order_id = item.get('exit_order_id') or item.get('order_id')
    
    entry_p = to_float(item.get('entry_price') or item.get('cost'))
    shares = abs(to_float(item.get('shares'), 1.0))
    exit_p = 0.0
    source = "UNKNOWN"

    # TIER 1: Query exact historical fill price from Tradier Broker Order History
    if order_id and account_id:
        order_url = f'https://sandbox.tradier.com/v1/accounts/{account_id}/orders/{order_id}'
        try:
            r = requests.get(order_url, headers=headers, timeout=3)
            if r.status_code == 200:
                ord_data = r.json().get('order', {})
                avg_price = to_float(ord_data.get('avg_fill_price'))
                if avg_price > 0:
                    exit_p = avg_price
                    source = "TRADIER_EXACT_FILL"
        except Exception:
            pass

    # TIER 2: Fallback to Market Quote Mark if Order History is unavailable/expired
    if exit_p == 0.0:
        quote_url = f'https://sandbox.tradier.com/v1/markets/quotes?symbols={occ_sym}'
        try:
            r = requests.get(quote_url, headers=headers, timeout=3)
            if r.status_code == 200:
                q = r.json().get('quotes', {}).get('quote', {})
                if isinstance(q, list) and len(q) > 0:
                    q = q[0]
                bid = to_float(q.get('bid'))
                last = to_float(q.get('last'))
                if bid > 0:
                    exit_p = bid
                    source = "QUOTE_BID_FALLBACK"
                elif last > 0:
                    exit_p = last
                    source = "QUOTE_LAST_FALLBACK"
        except Exception:
            pass

    # TIER 3: Safety Fallback to Entry Price
    if exit_p == 0.0:
        exit_p = entry_p
        source = "ENTRY_PRICE_SAFETY"

    pnl = round((exit_p - entry_p) * shares * 100.0, 2)

    table.update_item(
        Key={'tenant_id': tenant_id, 'trade_id': trade_id},
        UpdateExpression='SET entry_price = :ep, exit_price = :ex, net_pnl = :pnl, pnl_source = :src',
        ExpressionAttributeValues={
            ':ep': str(round(entry_p, 2)),
            ':ex': str(round(exit_p, 2)),
            ':pnl': str(round(pnl, 2)),
            ':src': source
        }
    )
    print(f'[✓] [{source}] {ticker} ({occ_sym}): Entry ${entry_p:.2f} -> Exit ${exit_p:.2f} | PnL: ${pnl:+.2f}')

print("\n[✓] Audit complete! All closed position PnLs recalculated and tagged.")
