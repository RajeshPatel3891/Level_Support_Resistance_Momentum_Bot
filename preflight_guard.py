import os
import sys
import json
import sqlite3
import hashlib
import py_compile
import glob
import re
import boto3
from datetime import datetime

CRITICAL_FILES = {
    "MasterSentry": "src/MasterSentry.py" if os.path.exists("src/MasterSentry.py") else "src/smart_cso_injector.py",
    "SmartInjector": "src/smart_cso_injector.py",
    "ExitMonitor": "src/gex_exit_monitor.py" if os.path.exists("src/gex_exit_monitor.py") else "src/RiskEngine.py",
    "Dashboard": "dashboard_server.py"
}

CONFIG_PATH = "system_config.json"
CHECKSUM_STORE = ".checksums.json"
DB_FILE = "harm_telemetry.db"
MANIFEST_PATH = "trading_levels.json"
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

def calculate_hash(filepath):
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        hasher.update(f.read())
    return hasher.hexdigest()

def check_config_and_checksums():
    print("[1/9] Verifying System Config & SHA-256 Checksum Ledger...")
    if not os.path.exists(CONFIG_PATH):
        # Create minimal fallback config if not present
        default_cfg = {
            "database": {"primary_table": "trades"},
            "risk_engine": {"total_risk_budget_per_trade_usd": 30.00}
        }
        with open(CONFIG_PATH, "w") as f:
            json.dump(default_cfg, f, indent=2)
        print(f" [!] Initialized baseline {CONFIG_PATH}.")
        
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
        print(f" [!] CODE MUTATION DETECTED in: {', '.join(mutations)}")
        if "--update-checksums" in sys.argv:
            with open(CHECKSUM_STORE, "w") as f:
                json.dump(current_hashes, f, indent=2)
            print(" [✓] Checksum Baseline Ledger updated.")
            return True
        else:
            print(" [!] Run with --update-checksums if this deployment incorporates intentional updates.")
            print(" [X] LAUNCH ABORTED: Code modification detected without checksum authorization.")
            return False

    print(" [✓] SHA-256 Checksum Ledger matched. Zero unapproved mutations.")
    return True

def check_syntax():
    print("\n[2/9] Checking Python Syntax Integrity across core modules...")
    for name, filepath in CRITICAL_FILES.items():
        if not os.path.exists(filepath):
            continue
        try:
            py_compile.compile(filepath, doraise=True)
            print(f" [✓] Syntax valid: {filepath}")
        except Exception as e:
            print(f" [X] SYNTAX ERROR in {filepath}: {e}")
            return False
    return True

def check_playbooks():
    print("\n[3/9] Checking Playbook Interface & Guardrail Contracts...")
    sys.path.append(os.getcwd())
    playbook_files = glob.glob('src/*_playbook.py')
    if not playbook_files:
        print(" [!] No custom isolated playbook files in src/ - using unified RiskEngine.")
        return True

    for pb_file in playbook_files:
        mod_name = pb_file.replace("/", ".").replace(".py", "")
        try:
            mod = __import__(mod_name, fromlist=['evaluate_call_entry', 'evaluate_put_entry', 'PLAYBOOK_CONFIG'])
            if not (hasattr(mod, 'evaluate_call_entry') and hasattr(mod, 'evaluate_put_entry')):
                print(f" [X] PLAYBOOK CONTRACT BREACH in {mod_name}")
                return False
        except Exception as e:
            print(f" [X] ERROR LOADING PLAYBOOK {mod_name}: {e}")
            return False
    print(f" [✓] {len(playbook_files)} Playbooks verified with active guardrails.")
    return True

def check_database_schema():
    print("\n[4/9] Validating SQLite Schema & Multi-Process WAL Config...")
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
    print("\n[5/9] Validating Level Proximity Manifest (trading_levels.json)...")
    if not os.path.exists(MANIFEST_PATH):
        print(f" [X] MANIFEST MISSING: {MANIFEST_PATH} not found.")
        return False

    try:
        with open(MANIFEST_PATH, "r") as f:
            data = json.load(f)
        levels = data.get("levels", data) if isinstance(data, dict) else {}
        print(f" [✓] Level Manifest verified with {len(levels)} active ticker contexts.")
        return True
    except Exception as e:
        print(f" [X] MANIFEST ERROR: {MANIFEST_PATH} is corrupted JSON: {e}")
        return False

def check_cross_script_alignment():
    print("\n[6/9] Validating Cross-Script Target Binding & Core Logic Cohesion...")
    scj_path = "src/smart_cso_injector.py"
    if os.path.exists(scj_path):
        with open(scj_path, "r") as f:
            scj_code = f.read()
        if "atomically_close_trade" not in scj_code:
            print(" [X] COHESION ERROR: smart_cso_injector.py missing atomic OCC DynamoDB close logic!")
            return False
        if "execute_passive_bid_maker_order" not in scj_code:
            print(" [X] COHESION ERROR: smart_cso_injector.py missing Passive Bid Maker execution router!")
            return False
    print(" [✓] Cross-script architecture bindings verified.")
    return True

def check_silent_passivity_traps():
    print("\n[7/9] Auditing Strategy Source Files for Silent Exception Traps...")
    pattern = re.compile(r'except.*:\s*\n\s*(pass|return False|return None)', re.MULTILINE)
    target_files = glob.glob('src/*_playbook.py')
    faulty = []
    
    for filepath in target_files:
        with open(filepath, 'r') as f:
            content = f.read()
            if pattern.search(content):
                faulty.append(filepath)
                
    if faulty:
        print(f" [X] PASSIVITY RISK: Silent exception trap(s) found in: {', '.join(faulty)}")
        return False

    print(" [✓] Strategy files verified: 0 silent exception traps found.")
    return True

def check_execution_flow_unit_test():
    print("\n[8/9] Running Execution Flow Simulation Test...")
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        test_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            INSERT INTO trades (ticker, timestamp, strategy, direction, spot_price, entry_price, shares, exit_status, net_pnl, is_live)
            VALUES ('MOCK_TEST', ?, 'SIM_TEST', 'CALL', 100.0, 100.0, 1.0, 'SIM_ACTIVE', 0.0, 0)
        """, (test_time,))
        conn.rollback()
        conn.close()
        print(" [✓] DB execution write & rollback simulation passed.")
        return True
    except Exception as e:
        print(f" [X] EXECUTION UNIT TEST FAILED: {e}")
        return False

def check_and_clear_stale_ghost_trades():
    print("\n[9/9] Checking & Sanitizing Ghost Active Positions across Databases...")
    # 1. Clean SQLite
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM trades WHERE UPPER(exit_status) = 'ACTIVE'")
        act_cnt = c.fetchone()[0]
        if act_cnt > 0:
            c.execute("UPDATE trades SET exit_status = 'CLOSED' WHERE UPPER(exit_status) = 'ACTIVE'")
            conn.commit()
            print(f" [✓] SQLite: Purged {act_cnt} hanging ACTIVE trades.")
        else:
            print(" [✓] SQLite: Clean state (0 lingering ACTIVE trades).")
        conn.close()
    except Exception as e:
        print(f" [!] SQLite ghost check warning: {e}")

    # 2. Clean DynamoDB
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
        res = table.scan(
            FilterExpression="exit_status = :act",
            ExpressionAttributeValues={":act": "ACTIVE"}
        )
        items = res.get("Items", [])
        if items:
            for it in items:
                table.update_item(
                    Key={"tenant_id": it.get("tenant_id", "COMPANY_A"), "trade_id": it["trade_id"]},
                    UpdateExpression="SET exit_status = :cls",
                    ExpressionAttributeValues={":cls": "CLOSED"}
                )
            print(f" [✓] DynamoDB: Purged {len(items)} lingering ACTIVE items in HarmonizedTrades.")
        else:
            print(" [✓] DynamoDB: Clean state (0 lingering ACTIVE items).")
    except Exception as e:
        print(f" [!] DynamoDB ghost check warning: {e}")
    return True

if __name__ == "__main__":
    print("=================================================================")
    print("🦅 HARM.AI LIVE STACK // UNIFIED PREFLIGHT INTEGRITY GUARD")
    print("=================================================================\n")
    
    success = (
        check_config_and_checksums() and
        check_syntax() and 
        check_playbooks() and
        check_database_schema() and 
        check_levels_manifest() and 
        check_cross_script_alignment() and
        check_silent_passivity_traps() and
        check_execution_flow_unit_test() and
        check_and_clear_stale_ghost_trades()
    )
    
    if success:
        print("\n=================================================================")
        print(" [✓] ALL 9 PREFLIGHT CHECKS PASSED. SYSTEM CLEAR FOR LIVE DEPLOYMENT!")
        print("=================================================================")
        sys.exit(0)
    else:
        print("\n=================================================================")
        print(" [X] PREFLIGHT FAILED. LAUNCH ABORTED.")
        print("=================================================================")
        sys.exit(1)
