import os
import sys
import json

# --- SYSTEM PATH RESOLUTION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

PARENT_DIR = os.path.dirname(CURRENT_DIR)
LEVELS_FILE = os.path.join(PARENT_DIR, 'trading_levels.json')

try:
    import LiveBot
except ImportError:
    print("[!] Critical Error: Could not resolve LiveBot.py from the /src path.")
    sys.exit(1)

def run_high_conviction_compliance_test():
    print("\n" + "="*75)
    print(" HARM.AI // AUTOMATED HIGH-CONVICTION ALERT COMPLIANCE RIG ")
    print("="*75)
    print(f"Target Manifest : {LEVELS_FILE}")
    print(f"Timestamp       : {LiveBot.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 75 + "\n")

    if not os.path.exists(LEVELS_FILE):
        print(f"[!] Error: Unable to locate levels file at {LEVELS_FILE}.")
        return

    with open(LEVELS_FILE, 'r') as f:
        manifest = json.load(f)
        levels_data = manifest.get("levels", {})

    print(f"Loaded levels manifest source: [{manifest.get('source', 'UNKNOWN')}]")
    print("-" * 75)
    print(f"{'Ticker':<8} | {'Support Floor':<13} | {'Sim Spot':<11} | {'Sim Vol':<9} | {'Expected':<10} | {'Outcome':<10}")
    print("-" * 75)

    pass_count = 0
    fail_count = 0
    skipped_count = 0

    # Ensure active trades tracking is cleared for a clean slate
    LiveBot.ACTIVE_TRADES = {}

    for ticker, config in levels_data.items():
        if ticker == "source":
            continue

        macro = config.get("algo_macro", {})
        support_list = macro.get("support", [])
        avg_vol = config.get("avg_volume", 1000)

        if not support_list:
            print(f"{ticker:<8} | {'No support':<13} | {'-':<11} | {'-':<9} | {'HIGH':<10} | {'SKIPPED'}")
            skipped_count += 1
            continue

        support_floor = float(support_list[0])

        sim_price = support_floor + 1.00
        sim_volume = int(avg_vol * 1.2)

        try:
            result = LiveBot.calculate_trade_conviction(
                ticker=ticker,
                current_price=sim_price,
                trade_side="LONG",
                curr_vol=sim_volume,
                conditions=["@"]
            )

            conviction = result.get("conviction")
            confidence = result.get("confidence", 0)
            action = result.get("action")

            if conviction == "HIGH" and action == "EXECUTE":
                outcome = "PASS ✅"
                pass_count += 1
            else:
                outcome = "FAIL ❌"
                fail_count += 1

            print(f"{ticker:<8} | ${support_floor:<12.2f} | ${sim_price:<10.2f} | {sim_volume:<9} | {'HIGH':<10} | {outcome:<10} ({conviction} @ {confidence}%)")

        except Exception as e:
            print(f"{ticker:<8} | [!] CRASH DETECTED DURING PARSING: {str(e)}")
            fail_count += 1

    print("-" * 75)
    print(f"Compliance Audit Summary: {pass_count} Passed | {fail_count} Failed | {skipped_count} Skipped")
    
    if fail_count == 0 and pass_count > 0:
        print("\n[✓] ALL CORE ENGINES SYSTEM COMPLIANT: High Conviction parameters are functional!")
    else:
        print("\n[!] WARNING: System anomalies or non-compliance detected. Review the calculations.")
    print("="*75 + "\n")

if __name__ == "__main__":
    run_high_conviction_compliance_test()
