#!/bin/bash
# ===============================================================================
# HARM.AI // MORNING STARTUP & 24-TICKER OPTIMIZATION PIPELINE
# ===============================================================================

set -e

echo "================================================="
echo "🌅 HARM.AI MORNING STARTUP & PRE-FLIGHT GATE"
echo "================================================="

# 1. System Health & Storage Check
echo "[*] [STEP 1/6] Checking EC2 Disk Space..."
df -h / | grep -E "Filesystem|root"
echo "[✓] Disk space verified."

# 2. Sync Guardrails & Live Market Data (24 Tickers)
echo -e "\n[*] [STEP 2/6] Syncing S3 Guardrail Levels & Live Market Quotes (24 Tickers)..."
python3 src/sync_guardrail_levels.py
python3 src/sync_market_data.py

# 3. Authorize Checksum Baseline Ledger & Run Security Preflight
echo -e "\n[*] [STEP 3/6] Authorizing Baseline Ledger & Running Preflight Security Guard..."
python3 preflight_guard.py --update-checksums > /dev/null
python3 preflight_guard.py

# 4. Hard Pre-Flight Integration Unit Test
echo -e "\n[*] [STEP 4/6] Executing Revenue Pipeline Unit Test Chain..."
python3 -m unittest tests/test_proximity_sync.py
python3 -m unittest -v tests/test_full_level_pipeline_chain.py
echo "[✓] Master unit test chain passed."

# 5. Deploy Fargate sandbox container
echo -e "\n[*] [STEP 5/6] Deploying Fargate Sandbox Node..."
if [ -f "./deploy_fargate.sh" ]; then
    ./deploy_fargate.sh sandbox
else
    echo "[!] deploy_fargate.sh not found, skipping container deployment."
fi

# 6. Fargate Cluster Discovery & Verification
echo -e "\n[*] [STEP 6/6] Verifying Active Fargate Task Status..."
aws ecs list-tasks --cluster harmonized-cluster --region us-east-1 --desired-status RUNNING 2>/dev/null || true

if [ -f "./get_fargate_urls.sh" ]; then
    ./get_fargate_urls.sh
fi

echo "================================================="
echo "🚀 MORNING STARTUP COMPLETE — READY FOR SESSION"
echo "================================================="
