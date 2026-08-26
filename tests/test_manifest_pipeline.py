import glob, os
#!/usr/bin/env python3
import json
import os
import sys
import importlib

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

MANIFEST = "trading_levels.json"

print("=" * 70)
print("🔍 HARM.AI INTEGRATION DIAGNOSTIC SUITE")
print("=" * 70)

# 1. READ CURRENT DISK STATE
print("\n[1/4] Auditing Current 'trading_levels.json' Disk State...")
if not os.path.exists(MANIFEST):
    print(f"❌ FAIL: {MANIFEST} does not exist!")
    sys.exit(1)

with open(MANIFEST, "r") as f:
    disk_data = json.load(f)

armed_count = 0
waiting_count = 0
for ticker, info in disk_data.items():
    status = info.get("status", "UNKNOWN")
    call_t = info.get("spot_target_call", 0)
    spot = info.get("spot", 0)
    if status == "ARMED":
        armed_count += 1
    else:
        waiting_count += 1
    print(f"  • {ticker:5s} | Spot: ${spot:<7.2f} | Status: {status:7s} | Call Target: ${call_t}")

print(f"  └─> Summary: {armed_count} ARMED, {waiting_count} WAITING")

# 2. TEST SYNC_MARKET_DATA EXECUTION
print("\n[2/4] Simulating 'src/sync_market_data.py' Execution...")
try:
    import src.sync_market_data as smd
    smd.sync()
    with open(MANIFEST, "r") as f:
        post_sync = json.load(f)
    print("  [✓] sync_market_data executed cleanly.")
    aapl_post = post_sync.get("AAPL", {})
    print(f"  [✓] Post-Sync AAPL Call Target: ${aapl_post.get('spot_target_call')} | Status: {aapl_post.get('status')}")
except Exception as e:
    print(f"  ❌ sync_market_data Error: {e}")

# 3. TEST PLAYBOOK DYNAMIC BINDINGS
print("\n[3/4] Validating All 24 Playbook Dynamic Binding Contracts...")
playbooks = [os.path.basename(f).replace("_playbook.py", "").lower() for f in glob.glob("src/playbooks/*_playbook.py")]
playbook_passes = 0

for p in playbooks:
    mod_name = f"src.{p}_playbook"
    try:
        mod = importlib.import_module(mod_name)
        call_fn = getattr(mod, "evaluate_call_entry", None)
        put_fn = getattr(mod, "evaluate_put_entry", None)
        has_dynamic = hasattr(mod, "_get_dynamic_target")
        
        if call_fn and put_fn and has_dynamic:
            playbook_passes += 1
            print(f"  [✓] {p.upper():4s}_playbook: Dynamic target function present & operational.")
        else:
            print(f"  ⚠️ {p.upper():4s}_playbook: Missing contract functions (Dynamic: {has_dynamic})")
    except Exception as e:
        print(f"  ❌ Exception loading {mod_name}: {e}")

print(f"  └─> Summary: {playbook_passes}/24 Playbooks Contract Validated.")

# 4. TRACE BACKGROUND OVERWRITE MUTATIONS
print("\n[4/4] Monitoring 'trading_levels.json' for Background Overwrite Mutations (5s probe)...")
import time
initial_mtime = os.path.getmtime(MANIFEST)
time.sleep(5)
post_mtime = os.path.getmtime(MANIFEST)

if post_mtime != initial_mtime:
    print("  ⚠️ ALERT: Background process IS actively modifying trading_levels.json right now!")
    with open(MANIFEST, "r") as f:
        mutated_data = json.load(f)
    print(f"  └─> Mutated AAPL Call Target: ${mutated_data.get('AAPL', {}).get('spot_target_call')}")
else:
    print("  [✓] No unauthorized background modifications detected during probe window.")

print("\n" + "=" * 70)
