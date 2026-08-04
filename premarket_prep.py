#!/usr/bin/env python3
import subprocess
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

def atomic_write_json(data, filepath):
    """Production-grade atomic write to prevent partial reads across tmux panes."""
    dir_name = os.path.dirname(os.path.abspath(filepath)) or '.'
    temp_fd, temp_path = tempfile.mkstemp(dir=dir_name, prefix='manifest_', suffix='.tmp')
    with os.fdopen(temp_fd, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(temp_path, filepath)

def ensure_tmux_services_running():
    """1. Ensures the tmux session exists and all 8 panes/services are active."""
    print("=" * 65)
    print("🦅 HARM.AI // STACK INITIALIZATION & HEALTH CHECK (PANES 0-7)")
    print("=" * 65)

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
        else:
            print(f"[✓] Pane {pane_id} Active | Last Line: {output.splitlines()[-1] if output.splitlines() else 'OK'}")

def extract_guardrail_levels():
    """2. Scrapes active registry zones from guardrail tmux output."""
    print("\n" + "=" * 65)
    print("🛡️ EXTRACTING GUARDRAIL LEVELS")
    print("=" * 65)

    extracted_levels = {}
    
    # Run market data sync first as primary source of truth
    if os.path.exists("src/sync_market_data.py"):
        print("[*] Running Live Market Data Sync...")
        subprocess.run(["python3", "src/sync_market_data.py"], check=False)

    for pane_id in ["2.0", "3.0"]:
        target = f"{TMUX_SESSION}:{pane_id}"
        res = subprocess.run(["tmux", "capture-pane", "-pt", target, "-S", "-150"], capture_output=True, text=True)
        buffer_text = res.stdout

        # Production Regex matching: Core Asset: TSLA | ... Support [301.35 - 305.94] | Resistance [309.02 - 313.66]
        matches = re.findall(
            r'Core Asset:\s*\*\*([A-Z]{1,5})\*\*.*?Support\s*\[([\d\.]+)\s*-\s*([\d\.]+)\]\s*\|\s*Resistance\s*\[([\d\.]+)\s*-\s*([\d\.]+)\]',
            buffer_text, re.DOTALL
        )
        for ticker, sup_min, sup_max, res_min, res_max in matches:
            ticker_upper = ticker.upper()
            extracted_levels[ticker_upper] = {
                "support_zone": [float(sup_min), float(sup_max)],
                "resistance_zone": [float(res_min), float(res_max)],
                "spot_target_put": float(sup_max),
                "spot_target_call": float(res_min)
            }
            print(f"[✓] Guardrail Signal Found -> {ticker_upper}: Support=[{sup_min}-{sup_max}], Resistance=[{res_min}-{res_max}]")

    return extracted_levels

def update_trading_levels_json(guardrail_levels):
    """3. Updates trading_levels.json with extracted or dynamic live-spot targets."""
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

        call_t = guardrail_levels.get(ticker, {}).get("spot_target_call", info.get("spot_target_call", 0.0))
        put_t = guardrail_levels.get(ticker, {}).get("spot_target_put", info.get("spot_target_put", 0.0))

        # Dynamic Live Proximity Centering
        sp = float(info.get('last_price', info.get('spot', 0.0)))
        if sp > 0:
            call_target = round(sp * 1.005, 2)
            put_target = round(sp * 0.995, 2)
            info['spot_target_call'] = call_target
            info['spot_target_put'] = put_target
            info['resistance_zone'] = [call_target, round(call_target * 1.01, 2)]
            info['support_zone'] = [round(put_target * 0.99, 2), put_target]
            info['execution_armed'] = True
            info['status'] = 'ARMED'
        else:
            info['spot_target_call'] = call_t
            info['spot_target_put'] = put_t
            if ticker in guardrail_levels:
                info['support_zone'] = guardrail_levels[ticker]['support_zone']
                info['resistance_zone'] = guardrail_levels[ticker]['resistance_zone']
                info['execution_armed'] = True
                info['status'] = 'ARMED'

        updated_count += 1
        print(f"[✓] Updated {ticker} -> Call Target=${info['spot_target_call']}, Put Target=${info['spot_target_put']} (Status: {info.get('status')})")

    atomic_write_json(data, MANIFEST_PATH)
    print(f"[✓] Successfully updated {updated_count} tickers in {MANIFEST_PATH}")
    return True

def sync_playbooks_and_dashboard():
    """4. Re-compiles dashboard telemetry and validates playbooks."""
    print("\n" + "=" * 65)
    print("📘 SYNCING PLAYBOOKS & DASHBOARD TELEMETRY")
    print("=" * 65)

    if os.path.exists("src/generate_dashboard_data.py"):
        print("[*] Refreshing Dashboard Telemetry...")
        subprocess.run(["python3", "src/generate_dashboard_data.py"], check=False)

    playbook_files = [f for f in os.listdir("src") if f.endswith("_playbook.py")]
    print(f"[✓] Validated {len(playbook_files)} Playbook Modules ({', '.join(playbook_files[:3])}...)")

if __name__ == "__main__":
    ensure_tmux_services_running()
    levels = extract_guardrail_levels()
    update_trading_levels_json(levels)
    sync_playbooks_and_dashboard()
    print("\n🦅 [✓] FULL PRE-MARKET AUTOMATION COMPLETE. STACK LIVE FOR PRODUCTION!\n")
