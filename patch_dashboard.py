import re

with open("dashboard_server.py", "r") as f:
    content = f.read()

# Replace static initial capital with dynamic rollover formula
old_pattern = r"INITIAL_BASE_CAPITAL\s*=\s*2000\.00"
new_code = "INITIAL_BASE_CAPITAL = 2760.96  # Rollover baseline from 07/23"

if re.search(old_pattern, content):
    content = re.sub(old_pattern, new_code, content)
    with open("dashboard_server.py", "w") as f:
        f.write(content)
    print("[✓] dashboard_server.py successfully patched!")
else:
    print("[!] Pattern not found or already patched. Proceeding to update checksums...")
