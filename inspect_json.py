import json
with open('trading_levels.json', 'r') as f:
    data = json.load(f)
    print(f"DEBUG: Data keys found: {list(data.keys())}")
    for symbol, config in data.get("levels", {}).items():
        has_tactical = "human_tactical" in config
        print(f"DEBUG: Checking {symbol} - Has human_tactical: {has_tactical}")
        if has_tactical:
            print(f"DEBUG: human_tactical keys: {list(config['human_tactical'].keys())}")
