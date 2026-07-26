import sys
import subprocess
import time

TICKERS = ["NVDA", "TSLA", "AAPL", "INTC", "RIVN", "SOFI", "AAL", "F", "PLTR"]

direction = "CALL"
extra_flags = []

# Parse arguments for direction and extra flags (e.g. --force)
for arg in sys.argv[1:]:
    if arg.upper() in ["CALL", "PUT"]:
        direction = arg.upper()
    else:
        extra_flags.append(arg)

print(f"🚀 [BATCH INJECTOR] Executing forced {direction} trades across all {len(TICKERS)} tickers...")
if extra_flags:
    print(f"⚡ Flags passed to Tactical Guard: {extra_flags}")

for ticker in TICKERS:
    print(f"\n--- Injecting Trade: {ticker} {direction} ---")
    cmd = [sys.executable, "force_trade_injector.py", ticker, direction] + extra_flags
    res = subprocess.run(cmd)
    time.sleep(1)

print("\n[✓] Batch injection complete. Check MasterSentry and Dashboard UI for updates!")
