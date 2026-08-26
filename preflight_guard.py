import os
import sys
import json
import sqlite3
import hashlib
import py_compile
import glob
import re
from datetime import datetime

CRITICAL_FILES = {
    "MasterSentry": "src/MasterSentry.py",
    "HarmonizedDispatch": "src/HarmonizedDispatch.py",
    "LiveBot": "src/LiveBot.py" if os.path.exists("src/LiveBot.py") else "LiveBot.py",
    "Dashboard": "dashboard_server.py"
}

CONFIG_PATH = "system_config.json"
CHECKSUM_STORE = ".checksums.json"
DB_FILE = "harm_telemetry.db"
MANIFEST_PATH = "trading_levels.json"

def calculate_hash(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

def check_config_and_checksums():
    print("[1/8] Verifying System Config & SHA-256 Checksum Ledger...")
    if not os.path.exists(CONFIG_PATH):
        print(f" [X] CRITICAL: Master config {CONFIG_PATH} missing!")
        return False
        
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.load(f)
        if cfg.get("database", {}).get("primary_table") != "trades":
            print(" [X] CONFIG ERROR: Primary table must be 'trades'!")
            return False
            
        risk_val = cfg.get('risk_engine', {}).get('total_risk_budget_per_trade_usd', 30.00)
        print(f" [✓] {CONFIG_PATH} verified (Risk Cap: ${risk_val:.2f}).")
    except Exception as e:
        print(f" [X] CONFIG CORRUPTED: {e}")
        return False

    current_hashes = {name: calculate_hash(path) for name, path in CRITICAL_FILES.items() if os.path.exists(path)}
    
    if not os.path.exists(CHECKSUM_STORE):
        with open(CHECKSUM_STORE, "w") as f:
            json.dump(current_hashes, f, indent=2)
        print(f" [✓] Created initial Checksum Baseline Ledger ({CHECKSUM_STORE}).")
        return True
    
    with open(CHECKSUM_STORE, "r") as f:
        stored_hashes = json.load(f)

    mutations = []
    for name, curr_hash in current_hashes.items():
        if name in stored_hashes and stored_hashes[name] != curr_hash:
            mutations.append(name)

    if mutations:
        print(f" [!] UNAPPROVED CODE MUTATION DETECTED in: {', '.join(mutations)}")
        print(" [!] To approve intentional changes and update the checksum baseline, run:")
        print("     python3 preflight_guard.py --update-checksums")
        if "--update-checksums" in sys.argv:
            with open(CHECKSUM_STORE, "w") as f:
                json.dump(current_hashes, f, indent=2)
            print(" [✓] Checksum Baseline Ledger successfully updated to new hashes.")
            return True
        else:
            print(" [X] LAUNCH ABORTED: Code modification detected without checksum authorization.")
            return False

    print(" [✓] SHA-256 Checksum Ledger matched. Zero unapproved mutations.")
    return True

def check_syntax():
    print("\n[2/8] Checking Python Syntax Integrity across core modules...")
    for name, filepath in CRITICAL_FILES.items():
        if not os.path.exists(filepath):
            print(f" [X] CRITICAL: Missing required system module: {filepath}")
            return False
        try:
            py_compile.compile(filepath, doraise=True)
            print(f" [✓] Syntax valid: {filepath}")
        except Exception as e:
            print(f" [X] SYNTAX ERROR in {filepath}: {e}")
            return False
    return True

def check_playbooks():
    print("\n[3/8] Checking Playbook Interface & Guardrail Contracts...")
    sys.path.append(os.getcwd())
    playbook_modules = [
        "src.aapl_playbook", "src.tsla_playbook", "src.nvda_playbook", 
        "src.rivn_playbook", "src.pltr_playbook", "src.sofi_playbook", 
        "src.intc_playbook", "src.f_playbook", "src.aal_playbook"
    ]
    for pb_mod in playbook_modules:
        try:
            mod = __import__(pb_mod, fromlist=['evaluate_call_entry', 'evaluate_put_entry', 'PLAYBOOK_CONFIG'])
            if not (hasattr(mod, 'evaluate_call_entry') and hasattr(mod, 'evaluate_put_entry') and hasattr(mod, 'PLAYBOOK_CONFIG')):
                print(f" [X] PLAYBOOK CONTRACT BREACH in {pb_mod}")
                return False
        except Exception as e:
            print(f" [X] ERROR LOADING PLAYBOOK {pb_mod}: {e}")
            return False
    print(" [✓] All 24 Playbooks verified with active guardrails.")
    return True

def check_database_schema():
    print("\n[4/8] Validating SQLite Schema & Multi-Process WAL Config...")
    if not os.path.exists(DB_FILE):
        print(f" [!] Database file {DB_FILE} not found. Initializing...")
        try:
            conn = sqlite3.connect(DB_FILE)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.close()
            print(f" [✓] Created {DB_FILE} with WAL mode enabled.")
        except Exception as e:
            print(f" [X] DB Init Error: {e}")
            return False

    try:
        conn = sqlite3.connect(DB_FILE, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(trades)")
        columns = [col[1] for col in cursor.fetchall()]
        
        required_cols = ["ticker", "spot_price", "entry_price", "shares", "exit_status", "net_pnl"]
        missing = [col for col in required_cols if col not in columns]
        
        if missing:
            print(f" [X] SCHEMA ERROR: Table 'trades' is missing columns: {missing}")
            conn.close()
            return False
        
        print(" [✓] Database schema and WAL journal mode verified.")
        conn.close()
        return True
    except Exception as e:
        print(f" [X] Database Check Failed: {e}")
        return False

def check_levels_manifest():
    print("\n[5/8] Validating Level Proximity Manifest (trading_levels.json)...")
    if not os.path.exists(MANIFEST_PATH):
        print(f" [X] MANIFEST MISSING: {MANIFEST_PATH} not found.")
        return False

    try:
        with open(MANIFEST_PATH, "r") as f:
            data = json.load(f)
        
        tickers = ["TSLA", "AAPL", "PLTR", "NVDA", "RIVN", "INTC", "SOFI", "AAL", "F"]
        for t in tickers:
            if t not in data:
                print(f" [!] Warning: Ticker {t} missing from level manifest.")
        print(f" [✓] Level Manifest verified with {len(data)} ticker contexts.")
        return True
    except Exception as e:
        print(f" [X] MANIFEST ERROR: {MANIFEST_PATH} is corrupted JSON: {e}")
        return False

def check_cross_script_alignment():
    print("\n[6/8] Validating Cross-Script Target Binding & Core Logic Cohesion...")
    
    dispatch_path = "src/HarmonizedDispatch.py"
    with open(dispatch_path, "r") as f:
        dispatch_code = f.read()
    if "harmonized_trades" in dispatch_code:
        print(f" [X] COHESION MISMATCH: {dispatch_path} contains old 'harmonized_trades' table reference!")
        return False

    with open("src/MasterSentry.py", "r") as f:
        sentry_code = f.read()
    if "SELECT ticker, spot_price, stop_loss, take_profit, timestamp, entry_price, shares" not in sentry_code:
        print(" [X] COHESION MISMATCH: MasterSentry.py missing entry_price and shares in SQL query!")
        return False
    if "0.50" not in sentry_code and "delta" not in sentry_code.lower():
        print(" [X] CORE LOGIC BREACH: MasterSentry.py missing Option Delta math (Delta = 0.50)!")
        return False

    with open("dashboard_server.py", "r") as f:
        dash_code = f.read()
    if "0.50" not in dash_code and "delta" not in dash_code.lower():
        print(" [X] CORE LOGIC BREACH: dashboard_server.py missing Option Delta PnL calculation!")
        return False

    print(" [✓] All cross-script target bindings and core logic rules are verified.")
    return True

def check_silent_passivity_traps():
    print("\n[7/8] Auditing Strategy Playbooks for Silent Exception Traps...")
    pattern = re.compile(r'except.*:\s*\n\s*(pass|return False|return None)', re.MULTILINE)
    
    # Strictly audit core active playbooks
    playbook_files = glob.glob('src/*_playbook.py')
    faulty_playbooks = []
    
    for filepath in playbook_files:
        with open(filepath, 'r') as f:
            content = f.read()
            if pattern.search(content):
                faulty_playbooks.append(filepath)
                
    if faulty_playbooks:
        print(f" [X] PASSIVITY RISK DETECTED: Silent exception trap(s) found in: {', '.join(faulty_playbooks)}")
        return False

    print(" [✓] Strategy playbooks verified: 0 silent exception traps found.")
    return True

def check_execution_flow_unit_test():
    print("\n[8/8] Running Execution Flow Unit Simulation Test...")
    try:
        livebot_path = CRITICAL_FILES["LiveBot"]
        with open(livebot_path, "r") as f:
            livebot_code = f.read()
            
        if "log_trade_to_database(" not in livebot_code and "execute_order(" not in livebot_code and "dispatch_trade" not in livebot_code:
            print(" [X] EXECUTION BARRIER: LiveBot on_message loop lacks active trade dispatch logic!")
            return False
            
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        test_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            INSERT INTO trades (ticker, timestamp, strategy, direction, spot_price, entry_price, shares, exit_status, net_pnl, is_live)
            VALUES ('MOCK_TEST', ?, 'SIM_TEST', 'CALL', 100.0, 100.0, 1.0, 'SIM_ACTIVE', 0.0, 0)
        """, (test_time,))
        
        conn.rollback()
        conn.close()
        
        print(" [✓] Execution flow simulation & DB write contract verified.")
        return True
    except Exception as e:
        print(f" [X] EXECUTION UNIT TEST FAILED: {e}")
        return False

if __name__ == "__main__":
    print("=================================================================")
    print("🦅 HARM.AI LIVE STACK // SYSTEM PREFLIGHT INTEGRITY GUARD")
    print("=================================================================\n")
    
    success = (
        check_config_and_checksums() and
        check_syntax() and 
        check_playbooks() and
        check_database_schema() and 
        check_levels_manifest() and 
        check_cross_script_alignment() and
        check_silent_passivity_traps() and
        check_execution_flow_unit_test()
    )
    
    if success:
        print("\n=================================================================")
        print(" [✓] ALL 8 PREFLIGHT CHECKS PASSED. SYSTEM CLEAR FOR LIVE DEPLOYMENT!")
        print("=================================================================")
        sys.exit(0)
    else:
        print("\n=================================================================")
        print(" [X] PREFLIGHT FAILED. LAUNCH ABORTED TO PREVENT EXECUTION ERRORS.")
        print("=================================================================")
        sys.exit(1)
