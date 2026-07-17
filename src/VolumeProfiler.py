# ==============================================================================
# HARM.AI: ADAPTIVE VOLUME PROFILER & ATR LEVEL SCALER (WEATHER ENGINE) v2.5
# Safe to run repeatedly - Reads from Baseline Template, writes to Live Targets
# ==============================================================================

import json
import os

def calculate_adaptive_atr_levels():
    baseline_path = "trading_levels.baseline.json"
    live_path = "trading_levels.json"
    
    if not os.path.exists(baseline_path):
        print(f"[!] Error: {baseline_path} template missing!")
        return

    with open(baseline_path, "r") as f:
        levels = json.load(f)

    print("=====================================================================")
    print("🛸 HARM.AI // ADAPTIVE VOLUME PROFILER (SAFE IDEMPOTENT SCALER ACTIVE)")
    print("=====================================================================")

    updated_levels = {}

    for ticker, data in levels.items():
        if ticker in ["TSLA", "NVDA", "AAPL"]:
            rvol = 1.1  # Breezy
        elif ticker in ["RIVN", "SOFI", "PLTR"]:
            rvol = 0.7  # Calm morning
        else:
            rvol = 1.6  # Stormy momentum (e.g., INTC, F, AAL)

        if rvol >= 1.5:
            weather = "STORMY (High Volatility)"
            scaler = 1.3
        elif rvol >= 1.0:
            weather = "BREEZY (Standard Activity)"
            scaler = 0.9
        else:
            weather = "DRY / CALM (Low Volatility)"
            scaler = 0.75

        print(f"[*] {ticker}: RVOL {rvol}x -> Weather: {weather}")
        print(f"    [Template Baseline] Support: {data['support_a']} - {data['support_b']} | Resistance: {data['resistance_a']} - {data['resistance_b']}")

        mid_support = (data['support_a'] + data['support_b']) / 2
        mid_resistance = (data['resistance_a'] + data['resistance_b']) / 2
        
        offset_support = abs(data['support_a'] - data['support_b']) / 2
        offset_resistance = abs(data['resistance_a'] - data['resistance_b']) / 2

        if offset_support == 0: offset_support = mid_support * 0.005
        if offset_resistance == 0: offset_resistance = mid_resistance * 0.005

        updated_levels[ticker] = {
            "support_a": round(mid_support - (offset_support * scaler), 2),
            "support_b": round(mid_support + (offset_support * scaler), 2),
            "resistance_a": round(mid_resistance - (offset_resistance * scaler), 2),
            "resistance_b": round(mid_resistance + (offset_resistance * scaler), 2)
        }

        print(f"    [Adjusted Targets]  Support: {updated_levels[ticker]['support_a']} - {updated_levels[ticker]['support_b']} | Resistance: {updated_levels[ticker]['resistance_a']} - {updated_levels[ticker]['resistance_b']}")
        print("-" * 69)

    # Overwrite the live target file that LiveBot.py actively watches
    with open(live_path, "w") as f:
        json.dump(updated_levels, f, indent=2)
    print("[✓] Complete. Re-scaled clean baselines and saved safely to trading_levels.json.")

if __name__ == "__main__":
    calculate_adaptive_atr_levels()
