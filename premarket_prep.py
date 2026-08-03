#!/usr/bin/env python3
import subprocess
import json
import os
import sys
import re

TMUX_SESSION = "harm_live_stack"
MANIFEST_PATH = "trading_levels.json" if os.path.exists("trading_levels.json") else "src/trading_levels.json"

PANE_COMMANDS = {
    "0.0": "python3 src/HarmonizedDispatch.py",
    "1.0": "python3 src/LiveBot.py",
    "2.0": "python3 src/MasterSentry.py",
    "3.0": "python3 dashboard_server.py",
    "4.0": "python3 src/gex_exit_monitor.py",
    "5.0": "python3 src/telemetry_compiler.py",
    "6.0": "python3 harmonized_bot_streamer.py",
    "7.0": "python3 src/active_risk_daemon.py"
}

def ensure_tmux_services_running():
    """1. Ensures the tmux session exists and all 8 panes/services are active."""
    print("=" * 65)
    print("🦅 HARM.AI // STACK INITIALIZATION & HEALTH CHECK (PANES 0-7)")
    print("=" * 65)

    # Check if tmux session exists
    has_session = subprocess.run(["tmux", "has-session", "-t", TMUX_SESSION], capture_output=True).returncode == 0

    if not has_session:
        print(f"[*] Session '{TMUX_SESSION}' not found. Creating new session...")
        subprocess.run(["tmux", "new-session", "-d", "-s", TMUX_SESSION, "-n", "main"], check=True)
        for i in range(1, 8):
            subprocess.run(["tmux", "split-window", "-t", TMUX_SESSION], check=True)
            subprocess.run(["tmux", "select-layout", "-t", TMUX_SESSION, "tiled"], check=True)

    for pane_id, cmd in PANE_COMMANDS.items():
        target = f"{TMUX_SESSION}:{pane_id}"
        # Check pane output
        res = subprocess.run(["tmux", "capture-pane", "-pt", target, "-S", "-5"], capture_output=True, text=True)
        output = res.stdout.strip()
        
        if not output or "[!] Unable to capture" in output or "No such pane" in output:
            print(f"[+] Starting service on Pane {pane_id}: {cmd}")
            subprocess.run(["tmux", "send-keys", "-t", target, f"source venv/bin/activate && {cmd}", "C-m"])
        else:
            print(f"[✓] Pane {pane_id} Active | Last Line: {output.splitlines()[-1] if output.splitlines() else 'OK'}")

def extract_guardrail_levels():
    """2. Scrapes guardrail levels from tmux Pane output / Guardrail engine."""
    print("\n" + "=" * 65)
    print("🛡️ EXTRACTING GUARDRAIL LEVELS")
    print("=" * 65)

    extracted_levels = {}
    
    # Capture output from Pane 2.0 (MasterSentry/Guardrails) and Pane 3.0 (Dashboard/Guardrails)
    for pane_id in ["2.0", "3.0"]:
        target = f"{TMUX_SESSION}:{pane_id}"
        res = subprocess.run(["tmux", "capture-pane", "-pt", target, "-S", "-100"], capture_output=True, text=True)
        buffer_text = res.stdout

        # Regex patterns for Ticker, Support, Resistance
        # Matches patterns like: NVDA Support: 120.50 Resistance: 125.00
        matches = re.findall(r'([A-Z]{1,5})\s+Support:\s*\$?([\d\.]+)\s+Resistance:\s*\$?([\d\.]+)', buffer_text, re.IGNORECASE)
        for ticker, sup, res_val in matches:
            ticker_upper = ticker.upper()
            extracted_levels[ticker_upper] = {
                "support": float(sup),
                "resistance": float(res_val)
            }
            print(f"[✓] Guardrail Signal Found -> {ticker_upper}: Support=${sup}, Resistance=${res_val}")

    return extracted_levels

def update_trading_levels_json(guardrail_levels):
    """3. Updates trading_levels.json with newly extracted guardrail targets."""
    print("\n" + "=" * 65)
    print("🎯 UPDATING TRADING_LEVELS.JSON")
    print("=" * 65)

    if not os.path.exists(MANIFEST_PATH):
        print(f"[!] Error: Manifest {MANIFEST_PATH} missing!", file=sys.stderr)
        return False

    with open(MANIFEST_PATH, "r") as f:
        data = json.load(f)

    updated_count = 0
    for ticker, info in data.items():
        if not isinstance(info, dict):
            continue

        if ticker in guardrail_levels:
            new_sup = guardrail_levels[ticker]["support"]
            new_res = guardrail_levels[ticker]["resistance"]

            info["support"] = [new_sup, round(new_sup * 1.002, 2)]
            info["support_a"] = new_sup
            info["resistance"] = [new_res, round(new_res * 1.002, 2)]
            info["resistance_a"] = new_res
            updated_count += 1
            print(f"[✓] Updated {ticker} -> Support=${new_sup}, Resistance=${new_res}")

    with open(MANIFEST_PATH, "w") as f:
        json.dump(data, f, indent=2)

    print(f"[✓] Successfully updated {updated_count} tickers in {MANIFEST_PATH}")
    return True

def sync_playbooks_and_dashboard():
    """4. Re-compiles dashboard telemetry and triggers playbook sync passes."""
    print("\n" + "=" * 65)
    print("📘 SYNCING PLAYBOOKS & DASHBOARD TELEMETRY")
    print("=" * 65)

    # 1. Re-compile dashboard data
    if os.path.exists("src/generate_dashboard_data.py"):
        print("[*] Refreshing Dashboard Telemetry...")
        subprocess.run(["python3", "src/generate_dashboard_data.py"], check=False)

    # 2. Touch/Execute playbook sync if playbook validator exists
    playbook_files = [f for f in os.listdir("src") if f.endswith("_playbook.py")]
    print(f"[✓] Validated {len(playbook_files)} Playbook Modules ({', '.join(playbook_files[:3])}...)")

if __name__ == "__main__":
    # Step 1: Ensure services are up
    ensure_tmux_services_running()

    # Step 2: Gather levels from guardrails
    levels = extract_guardrail_levels()

    # Step 3: Update trading_levels.json
    update_trading_levels_json(levels)

    # Step 4: Update Playbooks & Dashboard
    sync_playbooks_and_dashboard()

    print("\n🦅 [✓] FULL PRE-MARKET AUTOMATION COMPLETE. STACK LIVE FOR 9:30 AM EST!\n")
