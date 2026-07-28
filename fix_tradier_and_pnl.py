import re

new_quote_and_pnl = '''def get_live_quote(symbol):
    token = os.getenv("TRADIER_TOKEN") or os.getenv("TRADIER_SANDBOX_TOKEN")
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    try:
        r = requests.get(f"{base_url}/markets/quotes?symbols={symbol}", headers=headers, timeout=3)
        if r.status_code == 200:
            quote = r.json().get('quotes', {}).get('quote', {})
            return quote[0] if isinstance(quote, list) else quote
    except Exception as e:
        print(f"Tradier fetch error: {e}")
    return {}

def fetch_portfolio_state(page=1, selected_date=None, tenant_id='COMPANY_A'):
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
        ticker = trade_dict.get('ticker')
        
        # 1. Fetch live quote from Tradier
        quote = get_live_quote(ticker) if ticker else {}
        stored_spot = float(t.get('spot_price', 0.0))
        last_price = float(quote.get('last', stored_spot)) if quote.get('last') else float(t.get('price', stored_spot))
        
        entry = float(t.get('entry_price', t.get('basis', 0)))
        shares = float(t.get('shares', 1))
        direction = str(t.get('direction', 'CALL'))
        delta = 0.50
        
        # 2. Calculate PnL based on live stock price movement against entry spot
        base_ref = stored_spot if stored_spot > 0 else last_price
        spot_diff = (last_price - base_ref) if direction.upper() == 'CALL' else (base_ref - last_price)
        
        dollar_pnl = round(spot_diff * delta * 100 * shares, 2)
        position_cost = float(t.get('cost', entry * 100 * shares if entry < 50 else entry * shares))
        pnl_pct = (dollar_pnl / position_cost * 100.0) if position_cost > 0 else 0.0

        trade_dict['price'] = f"{last_price:.2f}"
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

pattern = r'def get_live_quote\(.*?\n    return active_trades, db_closed, total_pnl, total_closed_pnl, selected_date, starting_balance, settled_free, deployed_capital, unsettled'
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, new_quote_and_pnl, content, flags=re.DOTALL)
    with open('dashboard_server.py', 'w') as f:
        f.write(content)
    print('[✓] Patched get_live_quote and restored live delta PnL calculation!')
else:
    print('[!] Could not match pattern.')
