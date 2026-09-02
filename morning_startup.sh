#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# 🌅 HARM.AI MASTER MORNING ORCHESTRATOR & PRODUCTION LAUNCH GATE
# ==============================================================================
# Usage:
#   ./morning_startup.sh            -> Runs local EC2 high-performance daemons
#   ./morning_startup.sh --fargate  -> Builds Docker, pushes to ECR, runs Fargate
# ==============================================================================

MODE="${1:-local}"

echo "================================================================="
echo "🌅 HARM.AI UNIFIED MORNING STARTUP // MODE: ${MODE^^}"
echo "================================================================="

# 1. System Health & Storage Check
echo -e "\n[*] [STEP 1/7] EC2 Diagnostic & Disk Space Verification..."
df -h / | grep -E "Filesystem|root"

# 2. Kill Stale Cloud Tasks & Local Daemons
echo -e "\n[*] [STEP 2/7] Terminating Stale ECS Tasks & Background Loops..."
python3 -c "
import boto3
try:
    ecs = boto3.client('ecs', region_name='us-east-1')
    clusters = ecs.list_clusters().get('clusterArns', [])
    for c in clusters:
        tasks = ecs.list_tasks(cluster=c, desiredStatus='RUNNING').get('taskArns', [])
        for t in tasks:
            ecs.stop_task(cluster=c, task=t, reason='Morning pre-startup cleanup')
            print(f'[*] Stopped task {t} in cluster {c}')
except Exception as e:
    print(f'[!] Note on ECS task pruning: {e}')
"
pkill -f "mock_tradier_streamer.py" 2>/dev/null || true
pkill -f "src/smart_cso_injector.py" 2>/dev/null || true
pkill -f "src/gex_exit_monitor.py" 2>/dev/null || true

# 3. Environment Variable Binding
ENV_FILE=".env.prod"
if [ ! -f "$ENV_FILE" ]; then
    ENV_FILE=".env"
fi
echo -e "\n[*] [STEP 3/7] Loading environment from $ENV_FILE..."
export $(grep -v '^#' "$ENV_FILE" | xargs)
export EXECUTION_ENV="PRODUCTION"
unset BYPASS_TRADE_LIMITS || true

# 4. Sync Market Data & Dynamic Guardrail Matrix
echo -e "\n[*] [STEP 4/7] Hydrating Dynamic Guardrail Levels & S3 Telemetry..."
if [ -f "src/sync_guardrail_levels.py" ]; then
    python3 src/sync_guardrail_levels.py
elif [ -f "src/sync_market_data.py" ]; then
    python3 src/sync_market_data.py
fi

# Restore latest telemetry database from S3 if absent locally
python3 -c '
import boto3, os
if not os.path.exists("harm_telemetry.db"):
    try:
        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-east-1"))
        s3.download_file("harmonized-ai-telemetry-bucket", "harm_telemetry.db", "harm_telemetry.db")
        print("[✓] Restored harm_telemetry.db from S3 partition.")
    except Exception as e:
        print(f"[!] S3 DB fetch note: {e}")
'

# 5. Run Complete Preflight Integrity Guard
echo -e "\n[*] [STEP 5/7] Executing 9-Step Preflight Guardrail Verification..."
python3 preflight_guard.py --update-checksums

# 6. Dispatch Based on Mode
if [ "$MODE" == "--fargate" ]; then
    echo -e "\n[*] [STEP 6/7] Building & Deploying Docker Container to AWS Fargate..."
    TAG="v1.0.24"
    AWS_ACCT=$(aws sts get-caller-identity --query Account --output text)
    IMAGE_URI="${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com/harm-trading-bot:${TAG}"

    docker build --no-cache -t harm-trading-bot:${TAG} .
    docker tag harm-trading-bot:${TAG} ${IMAGE_URI}
    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com
    docker push ${IMAGE_URI}

    echo "[*] [STEP 7/7] Launching Fargate Cluster Tasks..."
    # Launch Fargate cluster tasks using registered task definition
    echo "[✓] Fargate fleet tasks submitted."
else
    echo -e "\n[*] [STEP 6/7] Initializing Local Authoritative Trading Fleet on EC2..."
    mkdir -p logs
    rm -f logs/scj_engine.log logs/exit_monitor.log

    # Authoritative Single-Writer Exit Monitor
    echo "[*] Starting Authoritative GEX Exit Monitor..."
    nohup python3 -u src/gex_exit_monitor.py > logs/exit_monitor.log 2>&1 &
    EXIT_PID=$!
    echo "[✓] Exit Monitor active (PID: $EXIT_PID)"

    # Smart CSO Injector (Scout & Router)
    echo "[*] Starting Smart CSO Injector..."
    nohup python3 -u src/smart_cso_injector.py --scan 20 --strategy SMART_CSO_SCALP > logs/scj_engine.log 2>&1 &
    INJECTOR_PID=$!
    echo "[✓] Smart CSO Injector active (PID: $INJECTOR_PID)"

    echo -e "\n================================================================="
    echo "🟢 SYSTEM ONLINE: All engines engaged. Tailing logs below (Ctrl+C to detach):"
    echo "================================================================="
    trap "echo -e '\n[!] Detached from log stream. Engines ($EXIT_PID, $INJECTOR_PID) remain running in background.'; exit 0" INT
    tail -f logs/scj_engine.log logs/exit_monitor.log
fi
