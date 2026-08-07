#!/usr/bin/env python3
import subprocess
import shutil
import json
import os
import sys
import re
import tempfile

TMUX_SESSION = "harm_live_stack"
MANIFEST_PATH = "trading_levels.json"

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

def purge_zombie_stacks():
    print("[🧹] Purging legacy processes...")
    if shutil.which("tmux"):
        try:
            subprocess.run(["tmux", "kill-server"], stderr=subprocess.DEVNULL)
        except Exception:
            pass
    if shutil.which("pkill"):
        subprocess.run(["pkill", "-9", "-f", "LiveBot.py"], stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "-f", "MasterSentry.py"], stderr=subprocess.DEVNULL)

def ensure_tmux_services_running():
    print("=" * 65)
    print("🦅 HARM.AI // STACK INITIALIZATION & HEALTH CHECK (PANES 0-7)")
    print("=" * 65)

    if not shutil.which("tmux"):
        print("[*] Tmux not found on system (Docker container mode). Skipping pane multiplexing.")
        return

    has_session = subprocess.run(["tmux", "has-session", "-t", TMUX_SESSION], capture_output=True).returncode == 0
    if not has_session:
        print(f"[*] Session '{TMUX_SESSION}' not found. Creating new session...")
        subprocess.run(["tmux", "new-session", "-d", "-s", TMUX_SESSION, "-n", "main"], check=True)
        for i in range(1, 8):
            subprocess.run(["tmux", "split-window", "-t", TMUX_SESSION], check=True)
            subprocess.run(["tmux", "select-layout", "-t", TMUX_SESSION, "tiled"], check=True)

    for pane_id, cmd in PANE_COMMANDS.items():
        target = f"{TMUX_SESSION}:{pane_id}"
        res = subprocess.run(["tmux", "capture-pane", "-pt", target, "-S", "-5"], capture_output=True, text=True)
        output = res.stdout.strip()
        if not output or "[!] Unable to capture" in output or "No such pane" in output:
            print(f"[+] Starting service on Pane {pane_id}: {cmd}")
            subprocess.run(["tmux", "send-keys", "-t", target, f"source venv/bin/activate && {cmd}", "C-m"])

def extract_guardrail_levels():
    print("\n" + "=" * 65)
    print("🛡️ EXTRACTING GUARDRAIL LEVELS")
    print("=" * 65)
    extracted_levels = {}
    if os.path.exists("src/sync_market_data.py"):
        subprocess.run(["python3", "src/sync_market_data.py"], check=False)
    return extracted_levels

def update_trading_levels_json(guardrail_levels):
    print("\n" + "=" * 65)
    print("🎯 UPDATING TRADING_LEVELS.JSON")
    print("=" * 65)
    if not os.path.exists(MANIFEST_PATH):
        return False
    with open(MANIFEST_PATH, "r") as f:
        data = json.load(f)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(data, f, indent=2)
    return True

def sync_playbooks_and_dashboard():
    print("\n" + "=" * 65)
    print("📘 SYNCING PLAYBOOKS & DASHBOARD TELEMETRY")
    print("=" * 65)
    if os.path.exists("src/generate_dashboard_data.py"):
        subprocess.run(["python3", "src/generate_dashboard_data.py"], check=False)

if __name__ == "__main__":
    purge_zombie_stacks()
    ensure_tmux_services_running()
    levels = extract_guardrail_levels()
    update_trading_levels_json(levels)
    sync_playbooks_and_dashboard()
    print("\n🦅 [✓] FULL PRE-MARKET AUTOMATION COMPLETE. STACK LIVE FOR PRODUCTION!\n")
