import re

with open("auto_inject_armed.py", "r") as f:
    code = f.read()

spread_guard_code = """
def validate_option_spread(quote, max_spread_pct=0.02):
    '''Reject option entries if the Bid-Ask spread exceeds max_spread_pct (default 2%).'''
    bid = float(quote.get('bid') or 0.0)
    ask = float(quote.get('ask') or 0.0)
    if ask <= 0 or bid <= 0:
        print(f"[⚠️ SPREAD GUARD] Invalid quotes for option: Bid=${bid}, Ask=${ask}")
        return False, 0.0
    
    spread_pct = (ask - bid) / ask
    if spread_pct > max_spread_pct:
        print(f"[⛔ SPREAD REJECT] Spread too wide ({spread_pct*100.0:.1f}% > {max_spread_pct*100.0:.1f}%). Bid=${bid}, Ask=${ask}")
        return False, bid
    
    return True, ask
"""

if "validate_option_spread" not in code:
    with open("auto_inject_armed.py", "w") as f:
        f.write(spread_guard_code + "\n" + code)
    print("[✓] Successfully injected 2% Max Bid-Ask Spread Guard into auto_inject_armed.py!")
else:
    print("[✓] Spread Guard is already active in auto_inject_armed.py.")
