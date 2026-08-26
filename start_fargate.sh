#!/bin/bash
set -e

echo "=========================================================="
echo "🚀 STARTING HARM.AI FARGATE CONTAINER (ENV: $EXECUTION_ENV)"
echo "=========================================================="

# 1. Background worker tasks
echo "[1/3] Launching background trading engine..."
python3 -u run_bot.py &

echo "[2/3] Launching GEX Exit Monitor..."
python3 -u run_gex_monitor.py &

# 2. Foreground Uvicorn process (keeps container alive on PID 1)
echo "[3/3] Starting Uvicorn Dashboard Server..."
exec python3 -m uvicorn dashboard_server:app --host 0.0.0.0 --port 8080 --log-level info
