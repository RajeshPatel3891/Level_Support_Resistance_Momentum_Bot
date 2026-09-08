import os
import re

target_file = "src/smart_cso_injector.py" if os.path.exists("src/smart_cso_injector.py") else "smart_cso_injector.py"

with open(target_file, "r") as f:
    code = f.read()

# 1. Ensure import of evaluate_orb_vwap_setup
if "evaluate_orb_vwap_setup" not in code:
    code = "from src.RiskEngine import evaluate_orb_vwap_setup\n" + code

# 2. Patch the Proximity Blocker block to attempt ORB_VWAP fallback
old_blocker = """print(f"[SCJ_ENGINE] [🛡️ PROXIMITY BLOCKER] Proximity Score {prox}% < 50.0% -> Execution Aborted.")"""

new_blocker = """print(f"[SCJ_ENGINE] [🛡️ PROXIMITY BLOCKER] GEX Proximity {prox}% < 50.0%. Checking ORB + VWAP Slope Sub-Engine...")
            # Fallback to ORB + VWAP Evaluation
            try:
                df_1min = fetch_intraday_bars(ticker, interval="1min") if 'fetch_intraday_bars' in globals() else None
                if df_1min is not None and not df_1min.empty:
                    orb_res = evaluate_orb_vwap_setup(df_1min, orb_minutes=15)
                    print(f"[SCJ_ENGINE] ⚡ [ORB_VWAP EVAL] {ticker} | Signal: {orb_res['signal']} | Reason: {orb_res['reason']}")
                    if orb_res['signal'] in ['BUY_CALL', 'BUY_PUT']:
                        execute_cso_order(ticker, orb_res['signal'], strategy_tag="ORB_VWAP")
            except Exception as orb_err:
                print(f"[SCJ_ENGINE] [!] ORB Evaluation error for {ticker}: {orb_err}")"""

if old_blocker in code:
    code = code.replace(old_blocker, new_blocker)
    with open(target_file, "w") as f:
        f.write(code)
    print(f"[✓] Successfully wired ORB + VWAP Slope fallback into {target_file}")
else:
    print("[!] Target proximity blocker statement not found or already patched.")
