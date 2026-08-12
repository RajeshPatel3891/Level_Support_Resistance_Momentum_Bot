import re

with open("smart_cso.py", "r") as f:
    code = f.read()

# Add spread validation directly before order placement
guard_function = """
def is_spread_valid(bid, ask, max_spread_pct=0.02):
    bid_f = float(bid or 0.0)
    ask_f = float(ask or 0.0)
    if ask_f <= 0 or bid_f <= 0:
        return False, 0.0
    spread_pct = (ask_f - bid_f) / ask_f
    return (spread_pct <= max_spread_pct), spread_pct
"""

if "is_spread_valid" not in code:
    code = guard_function + "\n" + code

# Inject check after option chain match
old_pattern = r"(print\(f\".*?\[✓ OPTION CHAIN MATCH\].*?\"\))"
replacement = r"""\1
    valid_spread, actual_spread_pct = is_spread_valid(bid, ask, 0.02)
    if not valid_spread:
        print(f"[⛔ SPREAD GUARD REJECT] Aborting entry for {ticker}! Bid=${bid}, Ask=${ask} (Spread: {actual_spread_pct*100.0:.2f}% > 2.00%)")
        return"""

if "SPREAD GUARD REJECT" not in code:
    code = re.sub(old_pattern, replacement, code)
    with open("smart_cso.py", "w") as f:
        f.write(code)
    print("[✓] Successfully injected hard 2.0% Spread Guard directly into smart_cso.py!")
else:
    print("[✓] smart_cso.py is already patched.")
