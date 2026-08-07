import time
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath('.'))

try:
    from src.gex_exit_monitor import evaluate_gex_exits
except ImportError:
    try:
        from gex_exit_monitor import evaluate_gex_exits
    except ImportError:
        print("[!] Could not import evaluate_gex_exits module.")
        sys.exit(1)

print("🚀 Starting Continuous GEX & MTTP Exit Daemon...")

while True:
    try:
        evaluate_gex_exits()
    except Exception as e:
        print(f"[⚠️] Exit Monitor Exception: {e}")
    
    time.sleep(10)  # Evaluate positions every 10 seconds
