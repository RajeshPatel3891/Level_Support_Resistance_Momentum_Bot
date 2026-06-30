import subprocess
import sys
import threading

def stream_output(process, prefix):
    """Reads output from a subprocess line by line and prints it with a prefix."""
    for line in iter(process.stdout.readline, ''):
        if line:
            sys.stdout.write(f"[{prefix}] {line}")
            sys.stdout.flush()
    process.stdout.close()

def run_master():
    print("[*] Launching Master Backtest Orchestrator...")

    # 1. Start the Live Shadow Advisor Process (--live)
    live_proc = subprocess.Popen(
        [sys.executable, "src/BacktestBot.py", "--live"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # 2. Start the Historical Backtest Engine Process
    hist_proc = subprocess.Popen(
        [sys.executable, "src/BacktestBot.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # 3. Spin up threads to handle stdout concurrently without blocking
    live_thread = threading.Thread(target=stream_output, args=(live_proc, "SHADOW-LIVE"))
    hist_thread = threading.Thread(target=stream_output, args=(hist_proc, "HISTORICAL"))

    live_thread.start()
    hist_thread.start()

    try:
        # Keep the master script alive while processes run
        # Historical will eventually finish, Live will run forever
        hist_proc.wait()
        print("[*] HISTORICAL Backtest Engine has completed its run.")
        
        # Keep waiting on the live stream
        live_proc.wait()
    except KeyboardInterrupt:
        print("\n[!] Master script interrupted. Terminating child processes cleanly...")
        live_proc.terminate()
        hist_proc.terminate()
        print("[*] All processes closed.")

if __name__ == "__main__":
    run_master()
