#!/usr/bin/env python3
"""
HARM.AI // GEX TELEMETRY HEARTBEAT & REGIME MONITOR
Executes sync_gex_lambda -> level_synthesizer -> updates heartbeat telemetry.
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEARTBEAT_PATH = os.path.join(BASE_DIR, "logs", "heartbeat_status.json")

def run():
    os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)
    t0 = time.time()
    
    # 1. Run sync_gex_lambda
    res1 = subprocess.run([sys.executable, os.path.join(BASE_DIR, "src", "sync_gex_lambda.py")], capture_output=True, text=True)
    if res1.returncode != 0:
        print(f"[-] Heartbeat Failed at sync_gex_lambda: {res1.stderr}")
        return

    # 2. Run level_synthesizer
    res2 = subprocess.run([sys.executable, os.path.join(BASE_DIR, "src", "level_synthesizer.py")], capture_output=True, text=True)
    if res2.returncode != 0:
        print(f"[-] Heartbeat Failed at level_synthesizer: {res2.stderr}")
        return

    # 3. Validate Master Manifest
    manifest_path = os.path.join(BASE_DIR, "trading_levels.json")
    try:
        with open(manifest_path, "r") as f:
            data = json.load(f)
        ticker_count = len(data)
    except Exception as e:
        ticker_count = 0
        data = {}

    status = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": time.time(),
        "elapsed_sec": round(time.time() - t0, 2),
        "status": "HEALTHY" if ticker_count >= 27 else "DEGRADED",
        "ticker_count": ticker_count,
        "sample_regimes": {
            "SPY": data.get("SPY", {}).get("gex_label"),
            "QQQ": data.get("QQQ", {}).get("gex_label"),
            "XLF": data.get("XLF", {}).get("gex_label")
        }
    }

    with open(HEARTBEAT_PATH, "w") as f:
        json.dump(status, f, indent=2)

    print(f"[✓] Heartbeat pulse recorded ({status['elapsed_sec']}s) - Tickers: {ticker_count} - SPY: {status['sample_regimes']['SPY']}")

if __name__ == "__main__":
    run()
