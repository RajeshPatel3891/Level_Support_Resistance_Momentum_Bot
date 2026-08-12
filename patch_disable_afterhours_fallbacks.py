import re

file_path = "./src/smart_cso_injector.py"

with open(file_path, "r") as f:
    code = f.read()

# Replace hardcoded quote defaults with a strict live-quote check
strict_quote_check = """
    if not bid or not ask or float(bid) <= 0 or float(ask) <= 0:
        print(f"[⛔ MARKET CLOSED / NO QUOTE] Aborting injection for {ticker}. Live options market is closed or quote unavailable.")
        return
"""

if "[⛔ MARKET CLOSED / NO QUOTE]" not in code:
    # Inject check before trade order placement/insertion
    code = re.sub(
        r'(def\s+inject_cso_trade[\s\S]*?:)',
        r'\1\n' + strict_quote_check,
        code
    )
    with open(file_path, "w") as f:
        f.write(code)
    print(f"[✓] Successfully patched {file_path} to block after-hours fallback entries!")
else:
    print(f"[✓] {file_path} already has market quote guard active.")
