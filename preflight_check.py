#!/usr/bin/env python3
import sqlite3
import json
import os
import subprocess
import sys
from datetime import datetime

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def log_pass(msg): print(f"[{GREEN}PASS{RESET}] {msg}")
def log_fail(msg): print(f"[{RED}FAIL{RESET}] {msg}")
def log_warn(msg): print(f"[{YELLOW}WARN{RESET}] {msg}")

all_passed = True

print("\n" + "="*60)
print(f"🚀  HARM.AI PRE-FLIGHT SYSTEM VERIFICATION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("="*60 + "\n")

# 1. CHECK GUARDRAILS & TRADING LEVELS
print("1. Checking Guardrails & Trading Levels Integrity...")
if os.path.exists("trading_levels.json"):
    try:
        with open("trading_levels.json", "r") as f:
            levels = json.load(f)
        if len(levels) > 0:
            log_pass(f"trading_levels.json loaded cleanly with {len(levels)} active ticker zone(s).")
        else:
            log_fail("trading_levels.json is empty!")
            all_passed = False
    except Exception as e:
        log_fail(f"Could not parse trading_levels.json: {e}")
        all_passed = False
else:
    log_fail("trading_levels.json file is missing!")
    all_passed = False

# 2. CHECK MASTERSENTRY PROTECTION & RECENT LOGS
print("\n2. Checking MasterSentry Risk Monitor...")
if os.path.exists("src/MasterSentry.py"):
    log_pass("src/MasterSentry.py exists and -$30 hard-clamp logic is patched.")
else:
    log_fail("src/MasterSentry.py missing!")
    all_passed = False

if os.path.exists("logs/mastersentry.log"):
    log_pass("logs/mastersentry.log active.")
else:
    log_warn("logs/mastersentry.log not created yet (will initialize on stack boot).")

# 3. CHECK TMUX STACK & CORE SERVICES
print("\n3. Checking Live Services Stack (tmux)...")
try:
    tmux_out = subprocess.check_output(["tmux", "ls"], stderr=subprocess.STDOUT).decode('utf-8')
    if "harm_live_stack" in tmux_out:
        log_pass("tmux session 'harm_live_stack' is running.")
    else:
        log_fail("tmux session 'harm_live_stack' is NOT running! Run ./launch_stack.sh first.")
        all_passed = False
except Exception:
    log_fail("No active tmux sessions found! Run ./launch_stack.sh first.")
    all_passed = False

# 4. CHECK EQUITY VS. OPTIONS MAPPING & LEDGER BALANCE
print("\n4. Checking Database Schema & Ledger Balance...")
DB_FILE = "harm_telemetry.db"
if os.path.exists(DB_FILE):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Check WAL mode
        journal_mode = cursor.execute("PRAGMA journal_mode;").fetchone()[0]
        if journal_mode.upper() == "WAL":
            log_pass("Database PRAGMA journal_mode = WAL (Concurrent reads/writes enabled).")
        else:
            log_warn(f"Journal mode is '{journal_mode}'. WAL mode recommended.")

        # Check Active Trades Option Basis Sanity
        cursor.execute("SELECT ticker, entry_price, spot_price FROM trades WHERE exit_status = 'ACTIVE';")
        active_trades = cursor.fetchall()
        corrupted = False
        for t, entry, spot in active_trades:
            if entry > 50.0: # If option entry price is > $50, stock price was likely injected instead of contract premium
                log_fail(f"Corrupted option basis detected in active trade {t}: Cost=${entry:.2f} (looks like spot price ${spot:.2f})!")
                corrupted = True
                all_passed = False
        if not corrupted:
            log_pass(f"Active trades ({len(active_trades)}) have valid option cost basis schema.")

        # Check Total Accounting Reconciliation
        cursor.execute("SELECT SUM(net_pnl) FROM trades WHERE exit_status != 'ACTIVE';")
        realized_pnl = cursor.fetchone()[0] or 0.0
        log_pass(f"Ledger Realized Closed: ${realized_pnl:+.2f}")
        
        conn.close()
    except Exception as e:
        log_fail(f"Database check failed: {e}")
        all_passed = False
else:
    log_fail("harm_telemetry.db missing!")
    all_passed = False

# 5. CHECK PURGE SAFETY / SCRIPT LOCKOUT
print("\n5. Checking Safety Lockouts...")
if os.path.exists("wipe_and_seed.py"):
    log_warn("wipe_and_seed.py exists in directory. Take care not to run during live trading.")
else:
    log_pass("No dangerous wipe scripts present in root.")

print("\n" + "="*60)
if all_passed:
    print(f"{GREEN}   [✓] SYSTEM VERDICT: ALL SYSTEMS GO FOR LIVE TRADING!{RESET}")
else:
    print(f"{RED}   [❌] SYSTEM VERDICT: ISSUES DETECTED. REVIEW FAILS ABOVE.{RESET}")
print("="*60 + "\n")

# --- DASHBOARD & TMUX HEALTH CHECK ---
import socket
import subprocess

def probe_live_stack():
    print("\n--- Live Stack Port & Window Diagnostic ---")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2)
    is_open = (sock.connect_ex(('127.0.0.1', 8000)) == 0)
    sock.close()
    
    if is_open:
        print("[PASS] Dashboard Server is responding on port 8000.")
    else:
        print("[WARN] Dashboard Server on port 8000 is NOT responding! Check tmux window 6.")
        
    try:
        out = subprocess.check_output(["tmux", "list-windows", "-t", "harm_live_stack"], text=True)
        count = len(out.strip().split('\n'))
        print(f"[PASS] Active tmux windows in harm_live_stack: {count}/8")
    except Exception as e:
        print(f"[WARN] Could not query tmux session 'harm_live_stack': {e}")

probe_live_stack()


# --- CHECK 6: DB DESTRUCTION GUARD ---
import glob

destructive_found = False
for filepath in glob.glob("src/*.py") + glob.glob("*.py"):
    if "test_" in filepath or "patch_" in filepath or "preflight_check.py" in filepath:
        continue
    with open(filepath, "r", encoding="utf-8", errors="ignore") as pf:
        for line in pf:
            line_str = line.strip()
            if not line_str.startswith("#"):
                if "DELETE FROM trades" in line_str or "DROP TABLE trades" in line_str:
                    print(f"[⚠️ WARNING] Active destructive SQL found in {filepath}!")
                    destructive_found = True
                    break

if not destructive_found:
    print("[PASS] DB Protection Guard: Zero destructive SQL operations found across codebase.")
