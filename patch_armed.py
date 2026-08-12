with open('dashboard_server.py', 'r') as f:
    code = f.read()

# Replace compound check with strict 1.0% gap arming
old_block = """                in_sup = (sup[0] <= spot <= sup[1]) if isinstance(sup, list) and len(sup) == 2 and sup[0] > 0 else False
                in_res = (res[0] <= spot <= res[1]) if isinstance(res, list) and len(res) == 2 and res[0] > 0 else False
                
                current_gap_pct = (gap_val / spot * 100.0) if spot > 0 and target_val > 0 else 999.0
                is_armed = bool(details.get('execution_armed')) or in_sup or in_res or (current_gap_pct <= 1.0)"""

new_block = """                current_gap_pct = (gap_val / spot * 100.0) if spot > 0 and target_val > 0 else 999.0
                is_armed = (current_gap_pct <= 1.0)"""

if old_block in code:
    code = code.replace(old_block, new_block)
    with open('dashboard_server.py', 'w') as f:
        f.write(code)
    print("[✓] Patched dashboard_server.py cleanly (Zero Orphan Variables).")
else:
    # Single-line fallback
    old_line = "is_armed = bool(details.get('execution_armed')) or in_sup or in_res or (current_gap_pct <= 1.0)"
    if old_line in code:
        code = code.replace(old_line, "is_armed = (current_gap_pct <= 1.0)")
        with open('dashboard_server.py', 'w') as f:
            f.write(code)
        print("[✓] Patched fallback line in dashboard_server.py.")
    else:
        print("[!] Target block/line not found or already patched.")
