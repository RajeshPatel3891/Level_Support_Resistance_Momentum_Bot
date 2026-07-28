with open('dashboard_server.py', 'r') as f:
    content = f.read()

old_check = "if trade_dict.get('status') == 'ACTIVE' or trade_dict.get('exit_status') == 'ACTIVE':"
new_check = "if trade_dict.get('status') == 'ACTIVE':"

if old_check in content:
    content = content.replace(old_check, new_check)
    with open('dashboard_server.py', 'w') as f:
        f.write(content)
    print('[✓] Tightened active trade filter in dashboard_server.py!')
