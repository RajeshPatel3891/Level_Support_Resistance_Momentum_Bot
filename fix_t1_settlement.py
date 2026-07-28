import re

with open('dashboard_server.py', 'r') as f:
    content = f.read()

# Replace return preparation in fetch_portfolio_state with T+1 settlement logic
old_prep = """    # Calculate active deployed capital dynamically from cost of active trades
    deployed_capital = sum(float(t.get('cost', 0.0)) for t in active_trades)
    
    # Settled Free Cash = Starting Balance - Deployed Capital + Realized Closed PnL
    settled_free = round(starting_balance - deployed_capital + total_closed_pnl, 2)"""

new_prep = """    # 1. Deployed Capital = sum of cost of active open positions
    deployed_capital = round(sum(float(t.get('cost', 0.0)) for t in active_trades), 2)
    
    # 2. Unsettled Cash = proceeds from closed trades today awaiting 24h settlement
    # Proceeds = Original Cost Outlay + Realized PnL
    today_closed_proceeds = sum(
        float(t.get('cost', 0.0)) + float(t.get('net_pnl', 0.0))
        for t in db_closed
    )
    unsettled = round(today_closed_proceeds, 2)
    
    # 3. Settled Free Cash = Starting Settled Cash minus active Deployed Capital
    settled_free = round(starting_balance - deployed_capital, 2)"""

if old_prep in content:
    content = content.replace(old_prep, new_prep)
    with open('dashboard_server.py', 'w') as f:
        f.write(content)
    print('[✓] Updated dashboard_server.py with T+1 24-hour settlement accounting!')
else:
    print('[!] Could not match prep block.')
