import json
import ijson
import os

def debug():
    ticker = "SPY"
    data_file = f"{ticker}_2026-07-07.json"
    if not os.path.exists(data_file):
        print(f"[!] {data_file} not found.")
        return

    with open("trading_levels.json", 'r') as f:
        level = json.load(f)["levels"]["SPY"]["human_tactical"]["breakout_trigger"]
    
    print(f"[*] SPY Breakout Trigger: {level}")
    
    with open(data_file, 'rb') as f:
        parser = ijson.items(f, 'item')
        prices = [float(t['price']) for t in parser if 'price' in t][:100]
        
    print(f"[*] First 100 prices in data: Min={min(prices)}, Max={max(prices)}")
    print(f"[*] Data intersects trigger? {min(prices) <= level <= max(prices)}")

debug()
