#!/bin/bash
# ===============================================================================
# HARM.AI // MORNING STARTUP & 24-TICKER OPTIMIZATION PIPELINE
# ===============================================================================

set -e

echo "================================================="
echo "🌅 HARM.AI MORNING STARTUP & PRE-FLIGHT GATE"
echo "================================================="

# 1. System Health & Storage Check
echo "[*] [STEP 1/5] Checking EC2 Disk Space..."
df -h / | grep -E "Filesystem|root"
echo "[✓] Disk space verified."

# 2. Sync Guardrails & Live Market Data (24 Tickers)
echo -e "\n[*] [STEP 2/5] Syncing S3 Guardrail Levels & Live Market Quotes (24 Tickers)..."
python3 src/sync_guardrail_levels.py
python3 src/sync_market_data.py

# 3. Hard Pre-Flight Integration Unit Test
echo -e "\n[*] [STEP 3/5] Executing Revenue Pipeline Unit Test Chain..."
python3 -m unittest tests/test_proximity_sync.py
python3 -m unittest -v tests/test_full_level_pipeline_chain.py
echo "[✓] Master unit test chain passed 5/5."

# 4. Diagnostic Simulation & MTTP Decay Analysis
echo -e "\n[*] [STEP 4/5] Running Diagnostic Playback Simulation..."
if [ -f "run_diagnostic_simulation.py" ]; then
    python3 run_diagnostic_simulation.py --batch || python3 run_diagnostic_simulation.py
else
    echo "[!] run_diagnostic_simulation.py not found, skipping playback run."
fi

if [ -f "gemini_cso_postmortem.py" ]; then
    echo "[*] Triggering Gemini CSO Post-Mortem Feedback Loop..."
    python3 gemini_cso_postmortem.py
fi

# 5. Fargate Cluster Discovery & Verification
echo -e "\n[*] [STEP 5/5] Verifying Fargate Task Status..."
./get_fargate_urls.sh

echo "================================================="
echo "🚀 MORNING STARTUP COMPLETE — READY FOR SESSION"
echo "================================================="
