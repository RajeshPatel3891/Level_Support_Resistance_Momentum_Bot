import argparse
import subprocess
import sys
import threading
from pathlib import Path

def stream_output(process, prefix):
    for line in iter(process.stdout.readline, ''):
        if line:
            sys.stdout.write(f"[{prefix}] {line}")
            sys.stdout.flush()
    process.stdout.close()

def run_master(target_date):
    # Unified Professional Banner
    print("\n" + "="*50)
    print(f" HARM.AI // UNIFIED MASTER BACKTEST ORCHESTRATOR ")
    print("="*50)
    print(f"Target Evaluation Session : {target_date}")
    print(f"Active Allocation Profile  : 5 Option Contracts ($500 base margin)")
    print("="*50 + "\n")

    print(f"[*] Launching Master Backtest Orchestrator for Date: {target_date}...")
    
    # Smart dynamic pathing resolution (Root vs src/ folders)
    script_dir = Path(__file__).resolve().parent
    if (script_dir / "src" / "BacktestBot.py").exists():
        backtest_bot_path = script_dir / "src" / "BacktestBot.py"
    elif (script_dir / "BacktestBot.py").exists():
        backtest_bot_path = script_dir / "BacktestBot.py"
    elif (script_dir.parent / "src" / "BacktestBot.py").exists():
        backtest_bot_path = script_dir.parent / "src" / "BacktestBot.py"
    else:
        print(f"[!] Error: Cannot resolve BacktestBot.py from execution path.")
        sys.exit(1)

    live_proc = subprocess.Popen(
        [sys.executable, str(backtest_bot_path), "--date", target_date, "--live"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    hist_proc = subprocess.Popen(
        [sys.executable, str(backtest_bot_path), "--date", target_date],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    # Spawn thread streams concurrently
    live_thread = threading.Thread(target=stream_output, args=(live_proc, "SHADOW-LIVE"))
    hist_thread = threading.Thread(target=stream_output, args=(hist_proc, "HISTORICAL"))

    live_thread.start()
    hist_thread.start()

    try:
        hist_proc.wait()
        print("[*] HISTORICAL Backtest Engine has completed its run.")
        live_proc.wait()
    except KeyboardInterrupt:
        print("\n[!] Master script interrupted. Terminating child processes cleanly...")
        live_proc.terminate()
        hist_proc.terminate()
        print("[*] All processes closed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Master Backtest Orchestrator")
    parser.add_argument("--date", default="2026-07-06", help="Date format YYYY-MM-DD")
    args = parser.parse_args()
    
    run_master(args.date)
