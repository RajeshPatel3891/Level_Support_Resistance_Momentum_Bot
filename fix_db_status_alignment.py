import re

with open('dashboard_server.py', 'r') as f:
    content = f.read()

# 1. Update active trade filter in fetch_portfolio_state
old_active_check = "if trade_dict.get('exit_status') == 'ACTIVE':"
new_active_check = "if trade_dict.get('status') == 'ACTIVE' or trade_dict.get('exit_status') == 'ACTIVE':"

if old_active_check in content:
    content = content.replace(old_active_check, new_active_check)

# 2. Update target trade match in close_position_in_db
old_close_match = "if item.get('ticker') == ticker_to_close and item.get('exit_status') == 'ACTIVE':"
new_close_match = "if item.get('ticker') == ticker_to_close and (item.get('status') == 'ACTIVE' or item.get('exit_status') == 'ACTIVE'):"

if old_close_match in content:
    content = content.replace(old_close_match, new_close_match)

# 3. Ensure both status and exit_status get set to CLOSED during updates
old_update_expr = "UpdateExpression='SET exit_status = :es, exit_price = :ep, net_pnl = :pnl, closed_at = :cat',"
new_update_expr = "UpdateExpression='SET exit_status = :es, #st = :es, exit_price = :ep, net_pnl = :pnl, closed_at = :cat',\n        ExpressionAttributeNames={'#st': 'status'},"

if old_update_expr in content:
    content = content.replace(old_update_expr, new_update_expr)

with open('dashboard_server.py', 'w') as f:
    f.write(content)

print('[✓] Standardized status and exit_status attribute handling in dashboard_server.py!')
