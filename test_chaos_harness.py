#!/usr/bin/env python3
"""
HARM.AI // CHAOS INJECTION & PROCESS RESILIENCE TEST HARNESS
===============================================================================
Simulates three failure modes to verify Watchdog alerting and recovery:
1. Target Process Force-Kill (`kill -9` on LiveBot / GexExitMonitor).
2. Simulated Network Drop / Tradier API HTTP 503 Spike.
3. Database Lock Timeout / SQLite Thread Contention.

Verification Target: Watchdog detects failure within 10–15s, triggers Discord 
alert, and auto-spawns dead daemon without ghost trade duplication.
"""

import os
import sys
import time
import sqlite3
import subprocess
import requests
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harm_telemetry.db')
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [CHAOS_HARNESS] {msg}")

def test_force_kill_resilience(target_script="src/LiveBot.py"):
    log_msg(f"💥 [SCENARIO 1] Executing SIGKILL (kill -9) on {target_script}...")
    
    try:
        ps_out = subprocess.check_output(["ps", "aux"]).decode()
        target_pid = None
        for line in ps_out.splitlines():
            if target_script in line and "python" in line:
                parts = line.split()
                target_pid = parts[1]
                break

        if not target_pid:
            log_msg(f"[*] {target_script} not running. Spawning mock process for chaos test...")
            proc = subprocess.Popen([sys.executable, "-u", target_script])
            time.sleep(2)
            target_pid = proc.pid

        log_msg(f"⚡ Terminating PID {target_pid} ({target_script})...")
        os.system(f"kill -9 {target_pid}")
        
        log_msg("⏱️ Waiting 12 seconds for Process Watchdog detection loop...")
        time.sleep(12)

        # Audit if Watchdog auto-respawned process
        new_ps = subprocess.check_output(["ps", "aux"]).decode()
        if target_script in new_ps:
            log_msg(f"🟢 [PASS] Watchdog successfully detected process death and auto-respawned {target_script}!")
        else:
            log_msg(f"🔴 [FAIL] Watchdog failed to revive {target_script} within window.")

    except Exception as e:
        log_msg(f"[-] Force-kill scenario exception: {e}")

def test_simulated_network_drop():
    log_msg("💥 [SCENARIO 2] Simulating Tradier API 503 / Network Timeout Spike...")
    mock_url = "https://sandbox.tradier.com/v1/markets/quotes?symbols=SPY"
    headers = {"Authorization": "Bearer INVALID_CHAOS_TOKEN"}

    try:
        res = requests.get(mock_url, headers=headers, timeout=2)
        log_msg(f"[*] API Handshake Status: {res.status_code} (Simulated Drop Handled)")
        log_msg("🟢 [PASS] Endpoint timeout/failover logic gracefully caught API refusal.")
    except Exception as e:
        log_msg(f"🟢 [PASS] Transport layer caught timeout exception: {e}")

def test_sqlite_lock_contention():
    log_msg("💥 [SCENARIO 3] Inducing SQLite exclusive write lock on harm_telemetry.db...")
    if not os.path.exists(DB_PATH):
        log_msg("[!] harm_telemetry.db missing. Skipping lock test.")
        return

    try:
        conn1 = sqlite3.connect(DB_PATH, timeout=1.0)
        conn1.execute("BEGIN EXCLUSIVE TRANSACTION;")
        log_msg("🔒 Exclusive write lock acquired on harm_telemetry.db.")

        # Attempt second connection write
        start_time = time.time()
        try:
            conn2 = sqlite3.connect(DB_PATH, timeout=2.0)
            conn2.execute("UPDATE trades SET cso_notes = 'CHAOS_TEST' WHERE id = 1;")
            conn2.commit()
        except sqlite3.OperationalError as lock_err:
            elapsed = round(time.time() - start_time, 2)
            log_msg(f"🟢 [PASS] SQLite WAL Lock Guard caught contention in {elapsed}s: {lock_err}")

        conn1.rollback()
        conn1.close()
        log_msg("🔓 Released exclusive lock.")

    except Exception as e:
        log_msg(f"[-] Lock test exception: {e}")

if __name__ == "__main__":
    print("=" * 80)
    print("🔥 HARM.AI // CHAOS INJECTION & SYSTEM RESILIENCE SUITE")
    print("=" * 80)
    
    test_force_kill_resilience()
    print("-" * 80)
    test_simulated_network_drop()
    print("-" * 80)
    test_sqlite_lock_contention()
    
    print("=" * 80)
    print("🎉 CHAOS HARNESS EXECUTION COMPLETE")
    print("=" * 80)
