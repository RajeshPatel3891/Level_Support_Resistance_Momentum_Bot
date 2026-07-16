#!/bin/bash

# Ensure the source directory structure exists
mkdir -p src

# ==========================================
# FILE 1: MACRO SYSTEM STATE MANIFEST
# ==========================================
echo "[*] Injecting macro_state.json into root directory..."
cat << 'EOF' > macro_state.json
{
"last_updated": "2026-07-02T11:00:00Z",
"macro_regime": "HIGH_VOLATILITY_SHOCK",
"primary_catalyst": "BLS Non-Farm Payrolls major miss (+57K vs expectations)",
"risk_bias": "RISK_OFF_LIQUIDATION",
"calendar_constraints": "Pre-holiday session (July 4th observance lockout tomorrow). Low structural liquidity, heavy institutional risk-off hedging.",
"operational_directive": "Enforce maximum defense. Rejects long support tests showing high velocity cascades; volume is likely distribution."
}
