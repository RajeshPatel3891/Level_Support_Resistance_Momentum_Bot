import re

with open('dashboard_server.py', 'r') as f:
    content = f.read()

# Replace the mismatched keyword argument call
old_call = """            cso_eval = evaluate_cso_informed_exit(
                spot=last_price,
                target=gex_target,
                stop_loss=stop_loss_val,
                hit_prob=hit_prob,
                option_pnl=dollar_pnl,
                shares=shares
            )"""

new_call = """            cso_eval = evaluate_cso_informed_exit(
                spot=last_price,
                target=gex_target,
                stop_loss=stop_loss_val,
                prob_win=hit_prob,
                floating_pnl=dollar_pnl,
                shares=shares,
                delta=delta
            )"""

if old_call in content:
    content = content.replace(old_call, new_call)
    with open('dashboard_server.py', 'w') as f:
        f.write(content)
    print('[✓] Aligned CSO parameter names: prob_win and floating_pnl!')
else:
    print('[!] Could not locate old CSO call block in dashboard_server.py')
