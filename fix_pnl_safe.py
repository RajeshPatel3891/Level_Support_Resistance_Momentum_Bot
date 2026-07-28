import re

restored_fetch_code = '''def fetch_portfolio_state(page=1, selected_date=None, tenant_id='COMPANY_A'):
    import boto3
    from boto3.dynamodb.conditions import Key
    from datetime import datetime

    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    trades_table = dynamodb.Table('HarmonizedTrades')
    ledger_table = dynamodb.Table('HarmonizedLedger')

    if not selected_date:
        selected_date = datetime.now().strftime('%Y-%m-%d')

    ledger_res = ledger_table.get_item(Key={'tenant_id': tenant_id, 'date': selected_date})
    ledger_item = ledger_res.get('Item', {})

    starting_balance = float(ledger_item.get('starting_settled_cash', '3430.22'))
    settled_free = float(ledger_item.get('available_settled_cash', '3430.22'))
    deployed_capital = float(ledger_item.get('deployed_capital', '0.00'))
    unsettled = float(ledger_item.get('unsettled_cash', '0.00'))
    total_closed_pnl = float(ledger_item.get('realized_pnl', '0.00'))

    trades_res = trades_table.query(
        KeyConditionExpression=Key('tenant_id').eq(tenant_id)
    )
    all_trades = trades_res.get('Items', [])

    active_trades = []
    db_closed = []
    total_floating_pnl = 0.0

    for t in all_trades:
        ts = str(t.get('timestamp', ''))
        trade_dict = dict(t)
        
        raw_net_pnl = float(t.get('net_pnl', 0.0))
        basis_val = float(t.get('basis', t.get('entry_price', 0.0)))
        shares_val = float(t.get('shares', 1.0))
        
        # Calculate position cost
        pos_cost = basis_val * shares_val * (100.0 if basis_val < 50.0 else 1.0)
        
        dollar_pnl = raw_net_pnl
        pnl_pct = (dollar_pnl / pos_cost * 100.0) if pos_cost > 0 else 0.0

        trade_dict['net_pnl'] = dollar_pnl
        trade_dict['pnl_pct'] = f"{pnl_pct:+.2f}%"
        trade_dict['dollar_pnl'] = f"${dollar_pnl:+.2f}"
        trade_dict['pnl_class'] = "text-emerald-400 font-bold" if dollar_pnl >= 0 else "text-rose-400 font-bold"
        trade_dict['exit_price'] = float(t.get('exit_price', 0)) if t.get('exit_price') else None

        if trade_dict.get('exit_status') == 'ACTIVE':
            active_trades.append(trade_dict)
            total_floating_pnl += dollar_pnl
        elif selected_date in ts:
            db_closed.append(trade_dict)

    total_pnl = total_floating_pnl if active_trades else float(ledger_item.get('floating_pnl', '0.00'))

    return active_trades, db_closed, total_pnl, total_closed_pnl, selected_date, starting_balance, settled_free, deployed_capital, unsettled'''

with open('dashboard_server.py', 'r') as f:
    content = f.read()

pattern = r'def fetch_portfolio_state\(.*?\n    return active_trades, db_closed, total_pnl, total_closed_pnl, selected_date, starting_balance, settled_free, deployed_capital, unsettled'
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, restored_fetch_code, content, flags=re.DOTALL)
    with open('dashboard_server.py', 'w') as f:
        f.write(content)
    print('[✓] Applied clean safe PnL mapping!')
else:
    print('[!] Could not match fetch_portfolio_state function pattern.')
