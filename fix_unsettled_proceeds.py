with open('dashboard_server.py', 'r') as f:
    content = f.read()

old_unsettled_calc = """    today_closed_proceeds = sum(
        float(t.get('cost', 0.0)) + float(t.get('net_pnl', 0.0))
        for t in db_closed
    )"""

new_unsettled_calc = """    # Calculate total gross proceeds (Principal Outlay + Net PnL)
    today_closed_proceeds = 0.0
    for t in db_closed:
        entry_cost = float(t.get('cost', 0.0))
        if entry_cost <= 0:
            entry_cost = float(t.get('shares', 1.0)) * float(t.get('entry_price', t.get('basis', 0.0))) * 100.0
        pnl = float(t.get('net_pnl', t.get('pnl', 0.0)))
        today_closed_proceeds += (entry_cost + pnl)
"""

if old_unsettled_calc in content:
    content = content.replace(old_unsettled_calc, new_unsettled_calc)
    with open('dashboard_server.py', 'w') as f:
        f.write(content)
    print('[✓] Updated proceeds math for Unsettled cash!')
else:
    print('[!] Could not match unsettled calc block.')
