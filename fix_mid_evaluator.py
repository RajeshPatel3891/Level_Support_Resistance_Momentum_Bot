import re

files_to_patch = ["dashboard_server.py", "telemetry_bridge.py", "run_gex_monitor.py"]

for file_path in files_to_patch:
    try:
        with open(file_path, "r") as f:
            code = f.read()
        
        # Replace bid-only live mark calculation with Midpoint calculation
        if 'q.get("bid"' in code or "q.get('bid'" in code:
            code = re.sub(
                r'float\(q\.get\(["\']bid["\'],?\s*0\.0\)\)',
                '(float(q.get("bid", 0.0)) + float(q.get("ask", 0.0))) / 2.0 if float(q.get("ask", 0.0)) > 0 else float(q.get("bid", 0.0))',
                code
            )
            with open(file_path, "w") as f:
                f.write(code)
            print(f"[✓] Patched {file_path} to evaluate Live Mark at MID-PRICE!")
    except FileNotFoundError:
        pass
