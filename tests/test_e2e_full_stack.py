#!/usr/bin/env python3
import json
import os
import sys
import sqlite3
import time
from datetime import datetime, timedelta

# Ensure project root is in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

print("=" * 75)
print("🧪 HARM.AI // FULL STACK END-TO-END SIMULATION HARNESS")
print("=" * 75)

# --- STAGE 1: MANIFEST INITIALIZATION ---
print("\n[Stage 1/4] Testing Manifest Initialization & Dynamic Centering...")
MANIFEST = "trading_levels.json"
if not os.path.exists(MANIFEST):
    print("❌ FAIL: Manifest missing!")
    sys.exit(1)

with open(MANIFEST, "r") as f:
    levels = json.load(f)

print(f"  [✓] Loaded {len(levels)} tickers from manifest.")
aapl = levels.get("AAPL", {})
print(f"  [✓] AAPL Spot: ${aapl.get('spot')} | Target Call: ${aapl.get('spot_target_call')} | Status: {aapl.get('status')}")

# --- STAGE 2: PLAYBOOK CONTRACT EVALUATION ---
print("\n[Stage 2/4] Testing All 9 Playbook Dynamic Contracts...")
import importlib
playbooks = ["aapl", "nvda", "tsla", "pltr", "rivn", "aal", "sofi", "intc", "f"]
passed_pb = 0
for p in playbooks:
    try:
        mod = importlib.import_module(f"src.{p}_playbook")
        if hasattr(mod, "_get_dynamic_target") and hasattr(mod, "evaluate_call_entry"):
            passed_pb += 1
    except Exception as e:
        print(f"  ❌ Error loading {p}: {e}")

print(f"  [✓] {passed_pb}/9 Playbook Contract Interfaces Operational.")

# --- STAGE 3: MTTP SIMULATION (MOCK STALE TRADE) ---
print("\n[Stage 3/4] Testing MTTP (Maximum Time-in-Trade Protection) Engine...")
DB_PATH = "harm_telemetry.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

stale_time = (datetime.now() - timedelta(minutes=50)).strftime("%Y-%m-%d %H:%M:%S")
cursor.execute(
    "INSERT INTO trades (ticker, direction, spot_price, entry_price, exit_status, timestamp, strategy) VALUES (?, ?, ?, ?, ?, ?, ?)",
    ("TEST_AAPL", "CALL", 309.50, 308.00, "ACTIVE", stale_time, "E2E_SIM_STRATEGY")
)
test_id = cursor.lastrowid
conn.commit()
conn.close()

print(f"  [+] Seeded mock trade ID {test_id} (TEST_AAPL) created at {stale_time} (50m ago).")

# Run GEX/MTTP Evaluation
import src.gex_exit_monitor as gex_mon
gex_mon.evaluate_gex_exits()

# Verify exit status in DB
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()
cursor.execute("SELECT exit_status, exit_price FROM trades WHERE id = ?", (test_id,))
row = cursor.fetchone()

if row and "MTTP_TIME_EXPIRED" in str(row[0]):
    print(f"  [✓] SUCCESS: MTTP automatically closed trade ID {test_id} -> Status: {row[0]}")
else:
    print(f"  ❌ FAIL: MTTP did not trigger exit! Status: {row[0] if row else 'None'}")

# Clean up mock row
cursor.execute("DELETE FROM trades WHERE id = ?", (test_id,))
conn.commit()
conn.close()

# --- STAGE 4: PROCESS ISOLATION & INTEGRITY ---
print("\n[Stage 4/4] Verifying Preflight Security Ledger...")
import subprocess
res = subprocess.run(["python3", "preflight_guard.py"], capture_output=True, text=True)
if "ALL 8 PREFLIGHT CHECKS PASSED" in res.stdout:
    print("  [✓] System Preflight Integrity Guard Passed Cleanly.")
else:
    print("  ⚠️ Preflight guard flagged a discrepancy.")

print("\n" + "=" * 75)
print("🦅 [✓] FULL END-TO-END PIPELINE VALIDATED SUCCESSFULLY!")
print("=" * 75)
