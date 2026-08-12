with open("dashboard_server.py", "r") as f:
    code = f.read()

# Replace stock symbol lookup for active positions with occ_symbol lookup
old_snippet = """                occ_sym = trade.get('occ_symbol') or trade.get('ticker')
                q = quotes.get(trade.get('ticker'), {})
                live_p = float(q.get('last') or trade.get('entry_price') or 1.0)"""

new_snippet = """                occ_sym = trade.get('occ_symbol') or trade.get('ticker')
                q = quotes.get(occ_sym) or quotes.get(trade.get('ticker'), {})
                live_p = float(q.get('ask') or q.get('last') or trade.get('entry_price') or 1.0)"""

if old_snippet in code:
    code = code.replace(old_snippet, new_snippet)
    with open("dashboard_server.py", "w") as f:
        f.write(code)
    print("[✓] Successfully patched dashboard_server.py to evaluate active trades via OCC Option Mark Prices!")
else:
    print("[!] Target pattern not found or already updated.")
