#!/usr/bin/env python3
import subprocess
import json
import os
import sys

def check_tmux_panes():
    print("=" * 65)
    print("🦅 HARM.AI // STACK HEALTH DIAGNOSTIC (TMUX PANES 0-7)")
    print("=" * 65)
    pane_labels = [
        "0.0: Orchestrator / Dispatch",
        "1.0: LiveBot Engine",
        "2.0: MasterSentry CSO",
        "3.0: Dashboard Server",
        "4.0: GEX Surface Sync",
        "5.0: Telemetry Compiler",
        "6.0: Tradier WS Stream",
        "7.0: System Monitor"
    ]
    
    for i in range(8):
        label = pane_labels[i] if i < len(pane_labels) else f"{i}.0"
        print(f"\n--- [PANE {label}] ---")
        try:
            res = subprocess.run(
                ["tmux", "capture-pane", "-pt", f"harm_live_stack:{i}.0", "-S", "-10"],
                capture_output=True, text=True, check=True
            )
            output = res.stdout.strip()
            print(output if output else "[EMPTY PANE OUTPUT]")
        except subprocess.CalledProcessError:
            print(f"[!] Unable to capture pane harm_live_stack:{i}.0 (Session active?)")
    print("\n" + "=" * 65)

def update_trading_levels():
    manifest_path = "trading_levels.json"
    if not os.path.exists(manifest_path):
        manifest_path = "src/trading_levels.json"
        
    if not os.path.exists(manifest_path):
        print(f"[-] Error: {manifest_path} not found!", file=sys.stderr)
        return

    with open(manifest_path, "r") as f:
        data = json.load(f)

    print("\n🎯 PRE-MARKET LEVEL PROXIMITY CONFIGURATOR")
    print("Press [ENTER] on any level to keep the current value.\n")

    updated = False
    for ticker, info in data.items():
        if not isinstance(info, dict):
            continue
            
        print(f"👉 [{ticker}] Current Spot: ${info.get('last_price', 0.0):.2f}")
        sup = info.get("support", [0.0, 0.0])
        res = info.get("resistance", [0.0, 0.0])
        
        # Support Target
        curr_sup = sup[0] if isinstance(sup, list) and len(sup) > 0 else 0.0
        new_sup = input(f"   Support Target (Current: ${curr_sup:.2f}): ").strip()
        if new_sup:
            try:
                val = float(new_sup)
                info["support"] = [val, round(val * 1.002, 2)]
                info["support_a"] = val
                updated = True
            except ValueError:
                print("   [!] Invalid number, keeping current.")

        # Resistance Target
        curr_res = res[0] if isinstance(res, list) and len(res) > 0 else 0.0
        new_res = input(f"   Resistance Target (Current: ${curr_res:.2f}): ").strip()
        if new_res:
            try:
                val = float(new_res)
                info["resistance"] = [val, round(val * 1.002, 2)]
                info["resistance_a"] = val
                updated = True
            except ValueError:
                print("   [!] Invalid number, keeping current.")

    if updated:
        with open(manifest_path, "w") as f:
            json.dump(data, f, indent=2)
        print("\n[✓] trading_levels.json successfully updated!")
        
        # Re-compile dashboard to reflect new targets immediately
        print("[*] Re-compiling dashboard telemetry...")
        subprocess.run(["./venv/bin/python3", "src/generate_dashboard_data.py"])
    else:
        print("\n[✓] No level changes made. Keeping current manifest.")

if __name__ == "__main__":
    check_tmux_panes()
    print("\n")
    update_trading_levels()
    print("\n🦅 [✓] PRE-MARKET PREP COMPLETE. READY FOR 9:30 AM EST OPEN!\n")
