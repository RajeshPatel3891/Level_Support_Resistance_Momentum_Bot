import re

with open("src/gex_exit_monitor.py", "r") as f:
    content = f.read()

# Update GSG Recovery to require at least +5% gain (or +$5) before locking breakeven recovery
old_rule = "if min_seen < 0.0 and dollar_pnl >= 1.00:"
new_rule = "if min_seen < 0.0 and pnl_pct >= 5.0 and dollar_pnl >= 5.00:"

if old_rule in content:
    content = content.replace(old_rule, new_rule)
    with open("src/gex_exit_monitor.py", "w") as f:
        f.write(content)
    print("[✓] GSG Recovery threshold updated to +5% / +$5.00 minimum profit!")
else:
    print("[!] Rule pattern not found or already updated.")
