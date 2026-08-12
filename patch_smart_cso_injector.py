import re

file_path = "./src/smart_cso_injector.py"

with open(file_path, "r") as f:
    code = f.read()

guard_function = """
def is_spread_valid(bid, ask, max_spread_pct=0.02):
    try:
        bid_f = float(bid or 0.0)
        ask_f = float(ask or 0.0)
        if ask_f <= 0 or bid_f <= 0:
            return False, 0.0
        spread_pct = (ask_f - bid_f) / ask_f
        return (spread_pct <= max_spread_pct), spread_pct
    except Exception:
        return False, 0.0
"""

if "def is_spread_valid" not in code:
    code = guard_function + "\n" + code

pattern = r"(print\(f\".*?\[✓ OPTION CHAIN MATCH\].*?\"\))"
replacement = r"""\1
    valid_spread, actual_spread_pct = is_spread_valid(bid, ask, 0.02)
    if not valid_spread:
        print(f"[⛔ SPREAD GUARD REJECT] Aborting entry for {ticker}! Bid=${bid}, Ask=${ask} (Spread: {actual_spread_pct*100.0:.2f}% > 2.00%)")
        return"""

if "SPREAD GUARD REJECT" not in code:
    code = re.sub(pattern, replacement, code)
    with open(file_path, "w") as f:
        f.write(code)
    print(f"[✓] Successfully patched {file_path} with 2.0% Max Spread Guard!")
else:
    print(f"[✓] {file_path} is already patched.")
