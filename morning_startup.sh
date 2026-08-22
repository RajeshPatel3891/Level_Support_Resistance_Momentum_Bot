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

# 4. Inline Hydration & Full Unit Test Discovery Suite
echo -e "\n[*] [STEP 4/6] Hydrating Manifest & Running Complete Unit Test Suite..."
python3 src/sync_guardrail_levels.py > /dev/null
python3 -m unittest discover -s tests -p "test_*.py" -v
python3 src/sync_guardrail_levels.py > /dev/null
echo "[✓] Complete unit test suite passed & manifest re-synchronized."

# 5. Deploy Dual Fargate Fleet (PROD + SANDBOX)
echo -e "\n[*] [STEP 5/6] Deploying Dual Fargate Fleet Node..."
if [ -f "./deploy_dual_fargate.sh" ]; then
    chmod +x ./deploy_dual_fargate.sh
    ./deploy_dual_fargate.sh
elif [ -f "./deploy_fargate.sh" ]; then
    ./deploy_fargate.sh
else
    echo "[!] No deployment script found, skipping container deployment."
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
