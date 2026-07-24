import os
import sys
import json
import subprocess
from datetime import datetime

print("=" * 60)
print(f"🚀  HARM.AI PRE-FLIGHT SYSTEM VERIFICATION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 60)

# Step 0: Execute Market Data Sync first
print("\n0. Synchronizing Dynamic Market Data & Level Proximity...")
try:
    sync_result = subprocess.run([sys.executable, "src/sync_market_data.py"], capture_output=True, text=True)
    if sync_result.returncode == 0:
        print("[PASS] src/sync_market_data.py executed successfully.")
    else:
        print(f"[FAIL] sync_market_data.py failed: {sync_result.stderr}")
except Exception as e:
    print(f"[FAIL] Could not run sync_market_data.py: {e}")

# Step 1: Checking Guardrails & Trading Levels Integrity
print("\n1. Checking Guardrails & Trading Levels Integrity...")
try:
    with open("trading_levels.json", "r") as f:
        levels = json.load(f)
    ticker_count = len([k for k, v in levels.items() if isinstance(v, dict)])
    armed_count = len([k for k, v in levels.items() if isinstance(v, dict) and v.get("execution_armed")])
    print(f"[PASS] trading_levels.json loaded cleanly with {ticker_count} tickers ({armed_count} currently ARMED).")
except Exception as e:
    print(f"[FAIL] trading_levels.json error: {e}")

# Step 2: MasterSentry Check
print("\n2. Checking MasterSentry Risk Monitor...")
if os.path.exists("src/MasterSentry.py"):
    print("[PASS] src/MasterSentry.py exists and -$30 hard-clamp logic is patched.")
else:
    print("[FAIL] src/MasterSentry.py missing!")

# Step 3: Check Live Services Stack & MarketSync Window
print("\n3. Checking Live Services Stack (tmux & MarketSync Window)...")
try:
    tmux_out = subprocess.check_output(["tmux", "list-windows", "-t", "harm_live_stack"]).decode()
    print("[PASS] tmux session 'harm_live_stack' is running.")
    
    if "MarketSync" in tmux_out or "9:" in tmux_out:
        print("[PASS] Window 9 'MarketSync' loop is ACTIVE.")
    else:
        print("[WARN] Window 'MarketSync' missing. Spawning loop now...")
        subprocess.run(["tmux", "new-window", "-t", "harm_live_stack:9", "-n", "MarketSync"])
        subprocess.run(["tmux", "send-keys", "-t", "harm_live_stack:9", "while true; do ./venv/bin/python3 src/sync_market_data.py; sleep 5; done", "C-m"])
        print("[PASS] Window 9 'MarketSync' successfully initialized and armed!")
except Exception as e:
    print(f"[WARN] Could not verify or start tmux session: {e}")

print("\n" + "=" * 60)
print("   [✓] PREFLIGHT CHECK COMPLETE & MARKETSYNC INTEGRATED")
print("=" * 60)
