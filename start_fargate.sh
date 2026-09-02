#!/bin/bash
set -e

echo "=========================================================="
echo "🚀 STARTING HARM.AI FARGATE CONTAINER (ENV: ${EXECUTION_ENV:-SANDBOX})"
echo "=========================================================="

export TENANT_ID="${TENANT_ID:-COMPANY_A_PROD}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

# 1. Hydrate Market Data & S3 Levels
echo "[1/4] Hydrating market quotes, S3 levels & SQLite telemetry..."
if [ -f "src/sync_market_data.py" ]; then
    python3 src/sync_market_data.py || true
fi

# Restore latest telemetry DB partition if available in S3
python3 -c '
import boto3, os
try:
    s3 = boto3.client("s3", region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
    s3.download_file("harmonized-ai-telemetry-bucket", "harm_telemetry.db", "harm_telemetry.db")
    print("[✓] Restored harm_telemetry.db from S3 partition.")
except Exception as e:
    print(f"[!] S3 Telemetry DB Sync Note: {e}")
' || true

# 2. Launch Authoritative Single-Writer Exit Monitor
echo "[2/4] Launching CSO Master Exit Monitor with auto-restart loop..."
(
  until 
    if [ -f "src/gex_exit_monitor.py" ]; then
      python3 -u src/gex_exit_monitor.py 2>&1
    elif [ -f "run_gex_monitor.py" ]; then
      python3 -u run_gex_monitor.py 2>&1
    else
      echo "[-] Exit monitor script missing." >&2 && exit 1
    fi
  do
    echo "[!] CSO Master Exit Monitor crashed with exit code $?. Respawning in 5s..." >&2
    sleep 5
  done
) &

# 3. Launch Smart CSO Injector (Scout & Router)
echo "[3/4] Launching Smart CSO Injector..."
if [ -f "src/smart_cso_injector.py" ]; then
    python3 -u src/smart_cso_injector.py --scan 20 --strategy SMART_CSO_SCALP &
elif [ -f "src/LiveBot.py" ]; then
    python3 -u src/LiveBot.py &
fi

# 4. Foreground Server Keeps Container Alive (PID 1)
echo "[4/4] Starting Uvicorn Dashboard Server..."
exec python3 -m uvicorn dashboard_server:app --host 0.0.0.0 --port 8080 --log-level info
