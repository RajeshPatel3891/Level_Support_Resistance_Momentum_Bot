import json, time, os, sys

LEVELS_FILE = "/home/ubuntu/Level_Support_Resistance_Momentum_Bot/trading_levels.json"

# --- SCENARIO LIBRARY ---
SCENARIOS = {
    # Scenario A: Strong upward trend -> Triggers Trailing Stops on pullback
    "trail": {
        "NVDA": [208.50, 225.00, 218.00, 205.00],
        "INTC": [99.50, 115.00, 110.00, 90.00]
    },
    # Scenario B: Sudden capitulation/dump -> Triggers strict Support B Stops
    "crash": {
        "NVDA": [208.50, 185.00, 160.00, 150.00],
        "INTC": [99.50, 85.00, 75.00, 70.00]
    },
    # Scenario C: Clean moonshot -> Smashes high Take Profit targets
    "moon": {
        "NVDA": [208.50, 260.00, 315.00, 320.00],
        "INTC": [99.50, 125.00, 155.00, 160.00]
    }
}

def inject_tick(scenario_name, step_index):
    if not os.path.exists(LEVELS_FILE):
        return False
    with open(LEVELS_FILE, 'r') as f:
        levels = json.load(f)

    timeline = SCENARIOS.get(scenario_name, SCENARIOS["trail"])
    active_updates = 0
    
    for ticker, prices in timeline.items():
        if step_index < len(prices) and ticker in levels:
            levels[ticker]["last_price"] = prices[step_index]
            active_updates += 1

    with open(LEVELS_FILE, 'w') as f:
        json.dump(levels, f, indent=2)

    return active_updates > 0

def run_simulation():
    # Read scenario from CLI argument (default to 'trail')
    scenario_name = sys.argv[1] if len(sys.argv) > 1 else "trail"
    if scenario_name not in SCENARIOS:
        print(f"⚠️ Unknown scenario '{scenario_name}'. Defaulting to 'trail'.")
        scenario_name = "trail"

    print("=====================================================================")
    print(f"🛸 HARM.AI // REPLAY SIMULATOR -> SCENARIO: {scenario_name.upper()}")
    print("=====================================================================")
    
    step = 0
    while True:
        print(f"[⌛ Step {step+1}] Broadcasting simulated price ticks...")
        has_more = inject_tick(scenario_name, step)
        if not has_more:
            print("[✓] Replay sequence complete.")
            break
        step += 1
        time.sleep(12)

if __name__ == "__main__":
    run_simulation()
