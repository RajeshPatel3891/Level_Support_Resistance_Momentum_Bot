import re

close_helper_code = '''
def close_position_in_db(ticker_to_close, exit_price=None, tenant_id='COMPANY_A'):
    import boto3
    from datetime import datetime
    
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    trades_table = dynamodb.Table('HarmonizedTrades')
    ledger_table = dynamodb.Table('HarmonizedLedger')
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # 1. Fetch trade
    trades_res = trades_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('tenant_id').eq(tenant_id)
    )
    items = trades_res.get('Items', [])
    target_trade = None
    for item in items:
        if item.get('ticker') == ticker_to_close and item.get('exit_status') == 'ACTIVE':
            target_trade = item
            break
            
    if not target_trade:
        print(f"[CLOSE ENGINE] No active trade found for {ticker_to_close}")
        return False

    trade_id = target_trade['trade_id']
    
    # 2. Get Live Quote if exit_price not specified
    if not exit_price or exit_price <= 0:
        quote = get_live_quote(ticker_to_close)
        stored_spot = float(target_trade.get('spot_price', 0.0))
        last_price = float(quote.get('last', stored_spot)) if quote.get('last') else stored_spot
    else:
        last_price = float(exit_price)
        
    stored_spot = float(target_trade.get('spot_price', 0.0))
    entry = float(target_trade.get('entry_price', target_trade.get('basis', 0)))
    shares = float(target_trade.get('shares', 1))
    direction = str(target_trade.get('direction', 'CALL'))
    delta = 0.50
    
    base_ref = stored_spot if stored_spot > 0 else last_price
    spot_diff = (last_price - base_ref) if direction.upper() == 'CALL' else (base_ref - last_price)
    realized_pnl = round(spot_diff * delta * 100 * shares, 2)
    
    # 3. Update Trade item in DynamoDB
    trades_table.update_item(
        Key={'tenant_id': tenant_id, 'trade_id': trade_id},
        UpdateExpression='SET exit_status = :es, exit_price = :ep, net_pnl = :pnl, closed_at = :cat',
        ExpressionAttributeValues={
            ':es': 'CLOSED',
            ':ep': str(last_price),
            ':pnl': str(realized_pnl),
            ':cat': datetime.now().isoformat()
        }
    )
    
    # 4. Update Ledger realized PnL
    ledger_res = ledger_table.get_item(Key={'tenant_id': tenant_id, 'date': today_str})
    ledger_item = ledger_res.get('Item', {})
    curr_realized = float(ledger_item.get('realized_pnl', '0.00'))
    new_realized = round(curr_realized + realized_pnl, 2)
    
    ledger_table.update_item(
        Key={'tenant_id': tenant_id, 'date': today_str},
        UpdateExpression='SET realized_pnl = :rp',
        ExpressionAttributeValues={':rp': str(new_realized)}
    )
    
    print(f"[✓ CLOSED POSITION] {ticker_to_close} | Exit Spot: ${last_price:.2f} | Realized PnL: ${realized_pnl:+.2f}")
    return True
'''

with open('dashboard_server.py', 'r') as f:
    content = f.read()

# Insert close_position_in_db function above fetch_portfolio_state
if 'def close_position_in_db' not in content:
    content = content.replace('def fetch_portfolio_state(', close_helper_code + '\ndef fetch_portfolio_state(')

# Update auto-close block inside fetch_portfolio_state
old_auto_trigger = """                if rec in ['EXIT_NOW', 'PROFIT_TAKE_TRIM', 'SL_TRIGGER', 'AUTO_CLOSE']:
                    print(f"[CSO AUTO-CLOSE TRIGGERED] {ticker} -> Signal: {rec} | PnL: ${dollar_pnl:+.2f}")
                    # If auto-close action function exists, call close_position_action(ticker)"""

new_auto_trigger = """                if rec in ['EXIT_NOW', 'PROFIT_TAKE_TRIM', 'TAKE_PROFIT_NOW', 'SL_TRIGGER', 'AUTO_CLOSE']:
                    print(f"[CSO AUTO-CLOSE TRIGGERED] {ticker} -> Signal: {rec} | PnL: ${dollar_pnl:+.2f}")
                    close_position_in_db(ticker, exit_price=last_price, tenant_id=tenant_id)"""

content = content.replace(old_auto_trigger, new_auto_trigger)

# Add FastAPI routes for close buttons
routes_code = '''
from fastapi.responses import RedirectResponse

@app.post("/close-position/{ticker}")
async def close_single_position(ticker: str):
    close_position_in_db(ticker)
    return RedirectResponse(url="/", status_code=303)

@app.post("/close-all")
async def close_all_positions():
    import boto3
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    trades_table = dynamodb.Table('HarmonizedTrades')
    res = trades_table.query(KeyConditionExpression=boto3.dynamodb.conditions.Key('tenant_id').eq('COMPANY_A'))
    for item in res.get('Items', []):
        if item.get('exit_status') == 'ACTIVE':
            close_position_in_db(item.get('ticker'))
    return RedirectResponse(url="/", status_code=303)
'''

if '@app.post("/close-position/{ticker}")' not in content:
    content = content.replace('if __name__ == \'__main__\':', routes_code + '\nif __name__ == \'__main__\':')

with open('dashboard_server.py', 'w') as f:
    f.write(content)

print('[✓] Integrated closure execution helper and POST endpoints into dashboard_server.py!')
