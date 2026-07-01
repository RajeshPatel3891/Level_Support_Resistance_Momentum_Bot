import os; from dotenv import load_dotenv; load_dotenv()
import subprocess
import sys
import threading
import time

def stream_output(process, prefix):
    # Use unbuffered line reading
    for line in iter(process.stdout.readline, ''):
        if line:
            sys.stdout.write(f"[{prefix}] {line}")
            sys.stdout.flush()

def run_orchestrator():
    print("[*] Launching Unified Sentry Orchestrator (Alpaca Data Link + ShadowBridge)...")

    # Start processes with unbuffered output
    # We use 'python3 -u' to force the child processes to be unbuffered
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    # Engine Swap: Swapping out the timed-out Massive poller for Alpaca WebSockets
    live_bot = subprocess.Popen(
        [sys.executable, "-u", "src/AlpacaPipeline.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env
    )

    shadow_bot = subprocess.Popen(
        [sys.executable, "-u", "src/BacktestBot.py", "--live"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env
    )

    t1 = threading.Thread(target=stream_output, args=(live_bot, "PRODUCER"), daemon=True)
    t2 = threading.Thread(target=stream_output, args=(shadow_bot, "SHADOW"), daemon=True)

    t1.start()
    t2.start()

    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] Shutting down Sentry suite...")
        live_bot.terminate()
        shadow_bot.terminate()

if __name__ == "__main__":
    run_orchestrator()
