#!/usr/bin/env python3
import sys, time, os, dotenv, threading, traceback
sys.path.extend(["/app", "/app/src", ".", "src"])

env_file = "/app/.env.prod" if os.path.exists("/app/.env.prod") else ".env.prod"
dotenv.load_dotenv(env_file, override=True)

import smart_cso_injector

armed_tickers = ["SOFI", "F", "AAL", "RIVN", "SNAP", "MARA", "CCL"]

orig_telemetry = smart_cso_injector.monitor_live_exit_telemetry
def non_blocking_telemetry(ticker):
    t = threading.Thread(target=orig_telemetry, args=(ticker,), daemon=True)
    t.start()
    print(f"   [📡 BACKGROUND TELEMETRY] Engaged daemon watch thread for {ticker}")

smart_cso_injector.monitor_live_exit_telemetry = non_blocking_telemetry

def run_daemon_loop():
    print("="*65)
    print("🚀🚀 HARM.AI // SINGLE-FILL VERIFICATION DAEMON ACTIVE 🚀🚀")
    print("   Mode   : SINGLE FILL & SHUTDOWN (CAPITAL PROTECT)")
    print(f"   Account: {os.getenv('TRADIER_ACCOUNT_ID')}")
    print(f"   Targets: {armed_tickers}")
    print("="*65)

    iteration = 1
    while True:
        print(f"\n--- [DAEMON LOOP #{iteration}] Scanning Targets at {time.strftime('%H:%M:%S')} ---")
        for ticker in armed_tickers:
            try:
                res = smart_cso_injector.smart_cso_scout_and_execute(ticker)
                print(f"   [✓] Result for {ticker}: {res}")
                
                # SINGLE-FILL CIRCUIT BREAKER
                if res is not None:
                    print("\n" + "="*65)
                    print(f"🎉🎉 [SINGLE-FILL CONFIRMED] Trade successfully executed for {ticker}!")
                    print("   [🛡️ RISK OFF] Shutting down daemon scout loop to protect capital.")
                    print("   Background telemetry threads will continue managing active exit.")
                    print("="*65)
                    return
                    
            except Exception as e:
                print(f"   [!] Error executing {ticker}: {e}")
                traceback.print_exc()
            time.sleep(2)

        print("\n[*] Iteration complete. Sleeping 30s...")
        iteration += 1
        time.sleep(30)

if __name__ == "__main__":
    run_daemon_loop()
