import subprocess
import time
import sqlite3
import json
import os
import sys

LEVELS_FILE = "trading_levels.json"
DB_FILE = "harm_telemetry.db"

def run_cmd(cmd, desc=None):
    if desc:
        print(f"\n⚡ [{desc}] Running: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"❌ Error: {result.stderr.strip()}")
    return result

def setup_environment():
    print("🧹 Cleaning up old monitor instances and resetting tape baselines...")
    subprocess.run("pkill -f gex_exit_monitor.py", shell=True)
    
    if os.path.exists(LEVELS_FILE):
        with open(LEVELS_FILE, 'r') as f:
            levels = json.load(f)
        if "NVDA" in levels: levels["NVDA"]["last_price"] = 208.50
        if "INTC" in levels: levels["INTC"]["last_price"] = 99.50
        with open(LEVELS_FILE, 'w') as f:
            json.dump(levels, f, indent=2)
            
    print("[✓] Environment reset successfully.")

def run_scenario(scenario_name):
    print(f"\n=====================================================================")
    print(f"🛸 HARM.AI // UNIFIED AUTOMATED INTEGRATION TEST: {scenario_name.upper()}")
    print(f"=====================================================================")
    
    setup_environment()
    
    print("\n🛰️ Launching hybrid exit monitor in the background...")
    monitor_proc = subprocess.Popen(
        ["./venv/bin/python3", "-u", "src/gex_exit_monitor.py"],
        stdout=open("monitor.log", "w"),
        stderr=subprocess.STDOUT
    )
    time.sleep(2)
    
    run_cmd("./venv/bin/python3 src/force_trade_injector.py NVDA CALL 208.50 5", "INJECT SIM POSITION")
    run_cmd("./venv/bin/python3 src/force_trade_injector.py INTC CALL 99.50 5 --live", "INJECT LIVE POSITION")
    
    time.sleep(2)
    
    # Forward the scenario name directly as an argument to the simulation tape!
    run_cmd(f"./venv/bin/python3 src/simulate_market_move.py {scenario_name}", "BROADCAST REPLAY SIMULATION TAPE")
    
    print("\n[⌛] Waiting for database locks and exit states to settle...")
    time.sleep(5)
    
    print("\n📊 [FINAL TELEMETRY RESULTS FROM HARM_TELEMETRY.DB]")
    print("-" * 80)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT ticker, exit_status, spot_price, stop_loss, net_pnl, is_live FROM trades ORDER BY timestamp DESC LIMIT 2;")
    rows = cursor.fetchall()
    
    for row in rows:
        mode = "LIVE" if row[5] == 1 else "SIM"
        print(f"[{mode}] {row[0]} | Status: {row[1]} | Entry: ${row[2]:.2f} | Final Stop Floor: ${row[3]:.2f} | Net PnL: {row[4]:+.4f}%")
    conn.close()
    print("-" * 80)

    monitor_proc.terminate()
    print("[✓] Integration test scenario suite wrapped up cleanly.\n")

if __name__ == "__main__":
    # Get scenario from command line argument, default to 'trail'
    chosen_scenario = sys.argv[1] if len(sys.argv) > 1 else "trail"
    run_scenario(chosen_scenario)
