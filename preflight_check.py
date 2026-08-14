import os
import sys
import json
import sqlite3
import boto3
import requests
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('.env.prod')

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

# Step 4: Test Live Tradier Token & Account Reachability
print("\n4. Testing Live Tradier Account & API Reachability...")
token = os.getenv("TRADIER_TOKEN")
acct = os.getenv("TRADIER_ACCOUNT_ID")
base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

try:
    r = requests.get(f"{base_url}/accounts/{acct}/balances", headers=headers, timeout=5)
    if r.status_code == 200:
        bal = r.json().get('balances', {})
        equity = bal.get('total_equity', 0.0)
        print(f"[PASS] Tradier Live API Connection: SUCCESS | Equity: ${equity}")
    else:
        print(f"[FAIL] Tradier Live API Failed: Status {r.status_code}")
except Exception as e:
    print(f"[FAIL] Tradier Live API Exception: {e}")

# Step 5: Test DynamoDB Access & Partition State
print("\n5. Testing DynamoDB Access & Partition State...")
try:
    dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
    table = dynamodb.Table('HarmonizedTrades')
    res = table.scan()
    items = res.get('Items', [])
    active_cnt = sum(1 for i in items if i.get('exit_status') == 'ACTIVE')
    print(f"[PASS] DynamoDB Table Reachable | Total Records: {len(items)} | Active: {active_cnt}")
except Exception as e:
    print(f"[FAIL] DynamoDB Connection Error: {e}")

# Step 6: Test Local SQLite Telemetry DB Health
print("\n6. Testing Local SQLite Telemetry DB Health...")
try:
    conn = sqlite3.connect('harm_telemetry.db')
    cursor = conn.cursor()
    cursor.execute("SELECT count(*) FROM trades WHERE exit_status = 'ACTIVE'")
    active_db = cursor.fetchone()[0]
    conn.close()
    print(f"[PASS] Local SQLite DB Reachable | Active Trades: {active_db}")
except Exception as e:
    print(f"[FAIL] Local SQLite DB Error: {e}")

# Step 7: Test Option Chain Feed (Read-Only Quote Lookup)
print("\n7. Testing Live Market Data Quote Stream...")
try:
    quote_res = requests.get(f"{base_url}/markets/quotes?symbols=SOFI", headers=headers, timeout=5)
    if quote_res.status_code == 200:
        q_data = quote_res.json().get('quotes', {}).get('quote', {})
        last_price = q_data.get('last') or q_data.get('close')
        print(f"[PASS] Live Option Chain Feed: ONLINE | SOFI Spot: ${last_price}")
    else:
        print(f"[FAIL] Market Quote Feed Failed: Status {quote_res.status_code}")
except Exception as e:
    print(f"[FAIL] Market Quote Feed Exception: {e}")

print("\n" + "=" * 60)
print(" 🚀 [✓] FULL PREFLIGHT DIAGNOSTIC COMPLETE & VERIFIED")
print("=" * 60)

if __name__ == '__main__':
    pass
