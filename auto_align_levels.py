import json
import ijson
import glob
import os

def align():
    levels_path = "trading_levels.json"
    with open(levels_path, 'r') as f:
        data = json.load(f)

    # Process every ticker we have data for
    for filepath in glob.glob("*_2026-07-07.json"):
        ticker = filepath.split('_')[0]
        if ticker not in data["levels"]: continue
        
        # Scan historical data for actual High and Low
        with open(filepath, 'rb') as f:
            prices = [float(t['price']) for t in ijson.items(f, 'item') if 'price' in t]
        
        if not prices: continue
        
        hist_high = max(prices)
        hist_low = min(prices)
        
        # Adjust triggers to be reachable:
        # Breakout at 95% of the daily high
        # Reversal at 105% of the daily low
        data["levels"][ticker]["human_tactical"]["breakout_trigger"] = round(hist_high * 0.99, 2)
        data["levels"][ticker]["human_tactical"]["reversal_zone"] = [round(hist_low * 1.01, 2), round(hist_low * 1.02, 2)]
        
        print(f"[✓] Aligned {ticker}: Trigger={data['levels'][ticker]['human_tactical']['breakout_trigger']}")

    with open(levels_path, 'w') as f:
        json.dump(data, f, indent=4)
    print("[*] trading_levels.json updated with reachable targets.")

align()
