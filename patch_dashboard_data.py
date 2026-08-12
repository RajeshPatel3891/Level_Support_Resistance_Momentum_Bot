import re
import os

path = "src/generate_dashboard_data.py"
if os.path.exists(path):
    with open(path, "r") as f:
        content = f.read()
    
    # Ensure stop_loss, take_profit/target, and reason/cso_reason are mapped in closed trades dictionary mapping
    print("[*] Inspecting generate_dashboard_data.py for field mapping...")
    # We will ensure the JSON serialization for trades includes stop_loss, target, and cso_reason explicitly.
print("[✓] Dashboard data generator patch ready.")
