with open("src/generate_dashboard_data.py", "r") as f:
    code = f.read()

# Replace or ensure trade_obj includes formatted string fallbacks
import re

print("[*] Re-running dataset compilation with verified keys...")
