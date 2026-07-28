import re

with open('dashboard_server.py', 'r') as f:
    content = f.read()

# Replace the static ledger assignments in fetch_portfolio_state
old_ledger_calc = """    starting_balance = float(ledger_item.get('starting_settled_cash', '3430.22'))
    settled_free = float(ledger_item.get('available_settled_cash', '3430.22'))
    deployed_capital = float(ledger_item.get('deployed_capital', '0.00'))
    unsettled = float(ledger_item.get('unsettled_cash', '0.00'))
    total_closed_pnl = float(ledger_item.get('realized_pnl', '0.00'))"""

new_ledger_calc = """    starting_balance = float(ledger_item.get('starting_settled_cash', '6535.24'))
    total_closed_pnl = float(ledger_item.get('realized_pnl', '0.00'))
    unsettled = float(ledger_item.get('unsettled_cash', '0.00'))"""

if old_ledger_calc in content:
    content = content.replace(old_ledger_calc, new_ledger_calc)

# Replace the return block area to calculate deployed & settled dynamically
old_return_prep = """    total_pnl = total_floating_pnl if active_trades else float(ledger_item.get('floating_pnl', '0.00'))

    return active_trades, db_closed, total_pnl, total_closed_pnl, selected_date, starting_balance, settled_free, deployed_capital, unsettled"""

new_return_prep = """    total_pnl = total_floating_pnl if active_trades else float(ledger_item.get('floating_pnl', '0.00'))

    # Calculate active deployed capital dynamically from cost of active trades
    deployed_capital = sum(float(t.get('cost', 0.0)) for t in active_trades)
    
    # Settled Free Cash = Starting Balance - Deployed Capital + Realized Closed PnL
    settled_free = round(starting_balance - deployed_capital + total_closed_pnl, 2)

    return active_trades, db_closed, total_pnl, total_closed_pnl, selected_date, starting_balance, settled_free, deployed_capital, unsettled"""

if old_return_prep in content:
    content = content.replace(old_return_prep, new_return_prep)
    with open('dashboard_server.py', 'w') as f:
        f.write(content)
    print('[✓] Integrated dynamic cash ledger accounting in dashboard_server.py!')
else:
    print('[!] Could not match return prep block.')
