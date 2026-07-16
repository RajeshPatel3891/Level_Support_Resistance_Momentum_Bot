import os
import json
import sys
from datetime import datetime

# Resolve absolute pathing relative to this file's directory
current_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
MACRO_STATE_PATH = os.path.join(current_dir, '..', 'macro_state.json')

def update_macro_state(regime, catalyst, risk_bias, constraints, directive):
    state_payload = {
        "last_updated": datetime.now().isoformat(),
        "macro_regime": regime,
        "primary_catalyst": catalyst,
        "risk_bias": risk_bias,
        "calendar_constraints": constraints,
        "operational_directive": directive
    }
    try:
        with open(MACRO_STATE_PATH, 'w') as f:
            json.dump(state_payload, f, indent=4)
        print(f"[✓] Macro State updated successfully at {state_payload['last_updated']}")
    except Exception as e:
        print(f"[X] Failed to persist macro state update: {e}")

print("[Macro Sentinel Background Daemon Active]")
update_macro_state(
    regime="HIGH_VOLATILITY_SHOCK",
    catalyst="BLS Non-Farm Payrolls major miss (+57K vs expectations)",
    risk_bias="RISK_OFF_LIQUIDATION",
    constraints="Pre-holiday session (July 4th observance lockout tomorrow). Low structural liquidity, heavy institutional risk-off hedging.",
    directive="Enforce maximum defense. Rejects long support tests showing high velocity cascades; volume is likely distribution."
)
