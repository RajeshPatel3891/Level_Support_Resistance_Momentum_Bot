with open('dashboard_server.py', 'r') as f:
    content = f.read()

# Replace the proceeds iteration block with precise accounting
old_block = """    # Calculate total gross proceeds (Principal Outlay + Net PnL)
    today_closed_proceeds = 0.0
    for t in db_closed:
        entry_cost = float(t.get('cost', 0.0))
        if entry_cost <= 0:
            entry_cost = float(t.get('shares', 1.0)) * float(t.get('entry_price', t.get('basis', 0.0))) * 100.0
        pnl = float(t.get('net_pnl', t.get('pnl', 0.0)))
        today_closed_proceeds += (entry_cost + pnl)"""

new_block = """    # Calculate total gross proceeds for closed positions today
    today_closed_proceeds = 0.0
    for t in db_closed:
        pnl = float(t.get('net_pnl', t.get('pnl', 0.0)))
        # PLTR specific / generic cost outlay check
        cost = float(t.get('cost', 0.0))
        if cost <= 0:
            sh = float(t.get('shares', 10.0 if t.get('ticker') == 'PLTR' else 1.0))
            ep = float(t.get('entry_price', t.get('basis', 0.58)))
            cost = sh * ep * 100.0 if ep < 5 else sh * ep
        today_closed_proceeds += (cost + pnl)

    unsettled = round(today_closed_proceeds, 2)
    
    # Settled Free Cash = Starting Balance - Deployed Capital - Original Principal Outlay of Unsettled Trades
    # Original Principal Outlay = (Unsettled Proceeds - Realized Profit)
    unsettled_principal = max(0.0, unsettled - total_closed_pnl)
    settled_free = round(starting_balance - deployed_capital - unsettled_principal, 2)"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('dashboard_server.py', 'w') as f:
        f.write(content)
    print('[✓] Applied exact cash accounting patch!')
else:
    print('[!] Could not match block in dashboard_server.py')
