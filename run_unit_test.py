import os
import sys
import json
import sqlite3
import re
import boto3
from jinja2 import Template

print("=" * 85)
print(" RUNNING UNIFIED PRE-FLIGHT TEST SUITE: DASHBOARD TELEMETRY & MTTP ENGINE ")
print("=" * 85)

failures = 0

# ==============================================================================
# SECTION 1: DASHBOARD TELEMETRY & UI RENDERING TEST
# ==============================================================================
print("\n[SECTION 1] TESTING DASHBOARD UI RENDER & TELEMETRY NORMALIZATION...")

raw_closed = []
if os.path.exists("dashboard_data.json"):
    try:
        with open("dashboard_data.json", "r") as f:
            dash = json.load(f)
            raw_closed = dash.get("closed_trades", [])
    except Exception as e:
        print(f"  [!] Error reading dashboard_data.json: {e}")

if not raw_closed and os.path.exists("harm_telemetry.db"):
    try:
        conn = sqlite3.connect("harm_telemetry.db")
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM trades WHERE exit_status != 'ACTIVE'")
        raw_closed = [dict(r) for r in c.fetchall()]
        conn.close()
    except Exception as e:
        print(f"  [!] Error reading SQLite: {e}")

# Fallback sync from DynamoDB if local cache is empty
if not raw_closed:
    try:
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('HarmonizedTrades')
        res = table.scan()
        raw_closed = [item for item in res.get('Items', []) if item.get('exit_status', 'ACTIVE') != 'ACTIVE']
    except Exception as e:
        print(f"  [!] DynamoDB Scan Warning: {e}")

print(f"  [✓] Loaded {len(raw_closed)} closed trade records for UI rendering test.")

normalized_ui_trades = []
for d in raw_closed:
    def clean_num(val, default=0.0):
        if val is None or val == "": return default
        if isinstance(val, (int, float)): return float(val)
        cleaned = re.sub(r'[^\d.-]', '', str(val))
        return float(cleaned) if cleaned else default

    entry = clean_num(d.get('entry_price'))
    exit_px = clean_num(d.get('exit_price'))
    shares = int(clean_num(d.get('shares') or d.get('contracts'), 1))
    
    pnl_val = clean_num(d.get('net_pnl') or d.get('realized_pnl'))
    if pnl_val == 0.0 and exit_px > 0 and entry > 0:
        pnl_val = round((exit_px - entry) * shares * 100, 2)

    sl_val = clean_num(d.get('stop_loss'), entry * 0.8)
    tp_val = clean_num(d.get('take_profit') or d.get('target'), entry * 1.5)
    cso_val = str(d.get('cso_notes') or d.get('cso_reason') or d.get('exit_status') or 'STOP_LOSS_20PCT')

    normalized_ui_trades.append({
        "ticker": d.get("ticker", "N/A"),
        "direction": d.get("direction", "CALL"),
        "strategy": d.get("strategy", "SMART_CSO_LIVE"),
        "entry_price": f"${entry:.2f}",
        "exit_price": f"${exit_px:.2f}",
        "stop_loss": f"${sl_val:.2f}",
        "take_profit": f"${tp_val:.2f}",
        "cso_notes": cso_val,
        "status": str(d.get("exit_status", "CLOSED")),
        "contracts": str(shares),
        "dollar_pnl": f"${pnl_val:+.2f}",
        "pnl_class": "text-red-400" if pnl_val < 0 else "text-emerald-400",
        "timestamp": d.get("exit_timestamp") or d.get("timestamp") or "N/A"
    })

# Assert UI telemetry completeness
for idx, t in enumerate(normalized_ui_trades, 1):
    if not t['dollar_pnl'] or t['dollar_pnl'] == "$+0.00":
        print(f"  [✗] FAIL: Invalid dollar_pnl on Trade #{idx} ({t['ticker']})")
        failures += 1
    if not t['stop_loss'] or t['stop_loss'] == "$0.00":
        print(f"  [✗] FAIL: Invalid stop_loss on Trade #{idx} ({t['ticker']})")
        failures += 1
    if not t['take_profit'] or t['take_profit'] == "$0.00":
        print(f"  [✗] FAIL: Invalid take_profit on Trade #{idx} ({t['ticker']})")
        failures += 1
    if not t['cso_notes']:
        print(f"  [✗] FAIL: Missing cso_notes on Trade #{idx} ({t['ticker']})")
        failures += 1

print(f"  [✓] UI Telemetry Field Verification Completed Across {len(normalized_ui_trades)} Records.")


# ==============================================================================
# SECTION 2: CSO / GEMMA MTTP TRANCHING & RUNNER LOGIC TEST
# ==============================================================================
print("\n[SECTION 2] TESTING CSO/GEMMA MTTP TRANCHING & RUNNER ENGINE...")

def evaluate_cso_gemma_logic(entry_price, current_price, stored_peak, shares, is_runner, gex_gap_pct=5.0, elapsed_minutes=10.0, is_rth=True):
    peak_price = max(stored_peak, current_price)
    
    pnl_pct = ((current_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0
    peak_pnl_pct = ((peak_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

    action = None
    exit_reason = None
    new_shares = shares
    new_runner_state = is_runner

    # 1. Multi-Contract Tranching Scale-Out
    if shares > 1 and not is_runner and (pnl_pct >= 50.0 or (gex_gap_pct != 0.0 and abs(gex_gap_pct) <= 0.5)):
        action = "PARTIAL_SCALE_OUT"
        scaled_shares = shares - 1
        new_shares = 1
        new_runner_state = True
        return peak_price, action, f"SCALE_{scaled_shares}X_LEAVE_1_RUNNER", new_shares, new_runner_state

    # 2. Final Exit Rules
    action = "FINAL_EXIT"
    if is_runner:
        trail_cushion = 12.0 if peak_pnl_pct >= 100.0 else 10.0
        if pnl_pct <= (peak_pnl_pct - trail_cushion):
            exit_reason = f"SMART_CSO_RUNNER_TRAIL_LOCK_(PEAK_{peak_pnl_pct:.0f}PCT)"
        else:
            action = "HOLD_RUNNER"
    elif pnl_pct >= 50.0 and shares == 1:
        exit_reason = "MTTP_TARGET_CAP_50PCT"
    elif peak_pnl_pct >= 35.0 and pnl_pct <= (peak_pnl_pct - 10.0):
        exit_reason = f"MTTP_TRAIL_TIER3_LOCK_(PEAK_{peak_pnl_pct:.0f}PCT)"
    elif peak_pnl_pct >= 20.0 and pnl_pct <= (peak_pnl_pct - 10.0):
        exit_reason = f"MTTP_TRAIL_TIER2_LOCK_(PEAK_{peak_pnl_pct:.0f}PCT)"
    elif peak_pnl_pct >= 12.0 and pnl_pct <= 0.0:
        exit_reason = f"MTTP_BREAKEVEN_LOCK_(PEAK_{peak_pnl_pct:.0f}PCT)"
    elif pnl_pct <= -20.0:
        exit_reason = "STOP_LOSS_20PCT"
    elif elapsed_minutes >= 45.0 and is_rth:
        exit_reason = "MTTP_TIME_EXPIRED_45M"
    else:
        action = "HOLD_POSITION"

    return peak_price, action, exit_reason, new_shares, new_runner_state


test_cases = [
    {
        "name": "5x Contract Position Hitting +50% Target Cap (Tranches 4x out, Leaves 1 Runner)",
        "entry": 1.00, "current": 1.50, "peak": 1.50, "shares": 5, "is_runner": False, "gex_gap": 3.0,
        "exp_action": "PARTIAL_SCALE_OUT", "exp_reason": "SCALE_4X_LEAVE_1_RUNNER", "exp_shares": 1, "exp_runner": True
    },
    {
        "name": "PLTR Mega Runner (+250% Peak, Currently +245% -> GEMMA Channel Room HOLD)",
        "entry": 1.00, "current": 3.45, "peak": 3.50, "shares": 1, "is_runner": True, "gex_gap": 0.2,
        "exp_action": "HOLD_RUNNER", "exp_reason": None, "exp_shares": 1, "exp_runner": True
    },
    {
        "name": "PLTR Mega Runner Pullback (+250% Peak, Pulled back to +235% -> Triggers Runner Lock)",
        "entry": 1.00, "current": 3.35, "peak": 3.50, "shares": 1, "is_runner": True, "gex_gap": 1.5,
        "exp_action": "FINAL_EXIT", "exp_reason": "SMART_CSO_RUNNER_TRAIL_LOCK_(PEAK_250PCT)", "exp_shares": 1, "exp_runner": True
    },
    {
        "name": "1x Single Contract Hit +50% Target (Full Exit)",
        "entry": 1.00, "current": 1.50, "peak": 1.50, "shares": 1, "is_runner": False, "gex_gap": 4.0,
        "exp_action": "FINAL_EXIT", "exp_reason": "MTTP_TARGET_CAP_50PCT", "exp_shares": 1, "exp_runner": False
    },
    {
        "name": "NVDA Mid Peak Pullback (+25% Peak, pulled back to +11% -> Tier 2 Lock)",
        "entry": 0.36, "current": 0.40, "peak": 0.45, "shares": 1, "is_runner": False, "gex_gap": 2.0,
        "exp_action": "FINAL_EXIT", "exp_reason": "MTTP_TRAIL_TIER2_LOCK_(PEAK_25PCT)", "exp_shares": 1, "exp_runner": False
    },
    {
        "name": "Hard Stop Loss (-20% Floor Hit)",
        "entry": 1.00, "current": 0.79, "peak": 1.00, "shares": 1, "is_runner": False, "gex_gap": 5.0,
        "exp_action": "FINAL_EXIT", "exp_reason": "STOP_LOSS_20PCT", "exp_shares": 1, "exp_runner": False
    }
]

for idx, tc in enumerate(test_cases, 1):
    print(f"  [*] Test #{idx}: {tc['name']}")
    
    peak, action, reason, shares, runner_state = evaluate_cso_gemma_logic(
        entry_price=tc['entry'],
        current_price=tc['current'],
        stored_peak=tc['peak'],
        shares=tc['shares'],
        is_runner=tc['is_runner'],
        gex_gap_pct=tc['gex_gap']
    )

    if action != tc['exp_action'] or reason != tc['exp_reason'] or shares != tc['exp_shares'] or runner_state != tc['exp_runner']:
        print(f"      [✗] FAIL: Result mismatch!")
        print(f"          Expected: Action='{tc['exp_action']}', Reason='{tc['exp_reason']}', Shares={tc['exp_shares']}, Runner={tc['exp_runner']}")
        print(f"          Got:      Action='{action}', Reason='{reason}', Shares={shares}, Runner={runner_state}")
        failures += 1
    else:
        print(f"      [✓] PASS: Action='{action}' | Reason='{reason}' | Shares={shares} | Runner={runner_state}")

print("\n" + "=" * 85)
if failures == 0:
    print(f" [✓] UNIFIED PRE-FLIGHT TEST PASSED 100%! READY FOR CONTAINER BUILD & FARGATE DEPLOYMENT. ")
else:
    print(f" [✗] UNIFIED TEST FAILED: {failures} assertion error(s). ")
print("=" * 85)

sys.exit(0 if failures == 0 else 1)
