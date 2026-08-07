#!/bin/bash
echo "[*] Launching Continuous GEX & MTTP Exit Daemon..."
python3 run_gex_monitor.py &

echo "[*] Launching Harmonized Dashboard Server..."
exec python3 -m uvicorn dashboard_server:app --host 0.0.0.0 --port 8000
