#!/usr/bin/env bash
set -euo pipefail

echo "================================================================="
echo "🌅 HARM.AI UNIFIED MORNING STARTUP // MODE: ${1:-local}"
echo "================================================================="

echo -e "\n[*] [STEP 1/5] EC2 Diagnostic & Disk Space Verification..."
df -h / | grep -E "Filesystem|root"

echo -e "\n[*] [STEP 2/5] Terminating Stale ECS Tasks & Background Loops..."
python3 -c "
import boto3
try:
    ecs = boto3.client('ecs', region_name='us-east-1')
    for c in ecs.list_clusters().get('clusterArns', []):
        for t in ecs.list_tasks(cluster=c, desiredStatus='RUNNING').get('taskArns', []):
            ecs.stop_task(cluster=c, task=t, reason='Startup cleanup')
except Exception:
    pass
" || true
pkill -f "src/smart_cso_injector.py" 2>/dev/null || true
pkill -f "src/gex_exit_monitor.py" 2>/dev/null || true

echo -e "\n[*] [STEP 3/5] Loading Environment & Hydrating S3 Levels..."
if [ -f ".env.prod" ]; then
    export $(grep -v '^#' .env.prod | xargs)
fi
python3 src/sync_guardrail_levels.py || python3 src/sync_market_data.py || true

echo -e "\n[*] [STEP 4/5] Executing 9-Step Preflight Guardrail Verification..."
python3 preflight_guard.py --update-checksums

if [ "${1:-local}" == "--fargate" ]; then
    echo -e "\n[*] [STEP 5/5] Building Docker & Deploying to AWS Fargate..."
    TAG="v1.0.24"
    AWS_ACCT=$(aws sts get-caller-identity --query Account --output text)
    IMAGE_URI="${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com/harm-trading-bot:${TAG}"

    docker build --no-cache -t harm-trading-bot:${TAG} .
    docker tag harm-trading-bot:${TAG} ${IMAGE_URI}
    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin ${AWS_ACCT}.dkr.ecr.us-east-1.amazonaws.com
    docker push ${IMAGE_URI}

    python3 scripts/deploy_fargate.py
    
    echo -e "\n[*] Verifying Fleet Deployment Health..."
    sleep 15
    if [ -f "./get_fargate_urls.sh" ]; then
        ./get_fargate_urls.sh
    fi
else
    echo -e "\n[*] [STEP 5/5] Launching Local Authoritative Trading Fleet..."
    mkdir -p logs
    nohup python3 -u src/gex_exit_monitor.py > logs/exit_monitor.log 2>&1 &
    nohup python3 -u src/smart_cso_injector.py --scan 20 --strategy SMART_CSO_SCALP > logs/scj_engine.log 2>&1 &
    echo "[✓] Local daemons active."
    tail -n 10 logs/scj_engine.log logs/exit_monitor.log
fi
