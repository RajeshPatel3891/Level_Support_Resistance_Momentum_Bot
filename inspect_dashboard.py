import re

with open("dashboard_server.py", "r") as f:
    code = f.read()

print("=" * 65)
print("🔍 DASHBOARD SERVER ENDPOINTS & STATE AUDIT")
print("=" * 65)

# Find routes / endpoints
routes = re.findall(r'@app\.route\(.*?\)\ndef \w+\(.*?\):', code)
print("[+] Found Routes:")
for r in routes:
    print(f"  • {r.replace(chr(10), ' ')}")

print("\n[+] Direct references to 'active' variables/functions:")
for line_num, line in enumerate(code.splitlines(), 1):
    if any(k in line.lower() for k in ['active_trades', 'active_positions', 'get_active', '/api', 'json']):
        print(f"  Line {line_num:3d}: {line.strip()}")

print("=" * 65)
