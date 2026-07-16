import os
import json
import sys

TICKERS = ["SPY", "QQQ", "NVDA", "IWM", "AMZN", "AAPL", "MSFT"]
TARGET_DATE = "2026-07-06"
LEVELS_FILE = "trading_levels.json"

def main():
    if not os.path.exists(LEVELS_FILE):
        print(f"[!] Error: {LEVELS_FILE} not found.")
        sys.exit(1)
        
    with open(LEVELS_FILE, "r") as f:
        levels_data = json.load(f)
        
    print("\n" + "="*60)
    print(" HARM.AI // TACTICAL SESSION LEVEL ALIGNER ")
    print("="*60)
    print(f"Target Session Date : {TARGET_DATE}")
    print("-" * 60)
    
    for ticker in TICKERS:
        data_file = f"{ticker}_{TARGET_DATE}.json"
        if not os.path.exists(data_file):
            print(f"{ticker:<6} : Tick data file '{data_file}' not found. Skipping.")
            continue
            
        with open(data_file, "r") as f:
            try:
                ticks = json.load(f)
            except Exception as e:
                print(f"{ticker:<6} : Error parsing JSON: {e}")
                continue
                
        if not ticks:
            print(f"{ticker:<6} : Tick dataset empty. Skipping.")
            continue
            
        prices = [float(t["price"]) for t in ticks]
        min_p = min(prices)
        max_p = max(prices)
        avg_p = sum(prices) / len(prices)
        
        # Derive tight, highly-reactive tactical triggers centered around today's volatility range
        breakout = round(avg_p + (max_p - avg_p) * 0.4, 2)
        reversal_low = round(min_p + (avg_p - min_p) * 0.15, 2)
        reversal_high = round(min_p + (avg_p - min_p) * 0.35, 2)
        
        # Inject directly into config cache
        if ticker in levels_data["levels"]:
            levels_data["levels"][ticker]["human_tactical"]["breakout_trigger"] = breakout
            levels_data["levels"][ticker]["human_tactical"]["reversal_zone"] = [reversal_low, reversal_high]
            
        print(f"{ticker:<6} : Range: ${min_p:.2f} - ${max_p:.2f} | Session Avg: ${avg_p:.2f}")
        print(f"         ├─ Set Breakout trigger : ${breakout:.2f}")
        print(f"         └─ Set Reversal zone    : [${reversal_low:.2f}, ${reversal_high:.2f}]")
        
    # Save the aligned config back to disk
    levels_data["source"] = f"Automated_Intraday_Alignment_{TARGET_DATE}"
    with open(LEVELS_FILE, "w") as f:
        json.dump(levels_data, f, indent=4)
        
    print("-" * 60)
    print("[✓] trading_levels.json updated with high-fidelity triggers!")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
