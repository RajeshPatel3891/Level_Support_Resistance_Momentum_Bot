import json

levels_file = "trading_levels.json"

with open(levels_file, "r") as f:
    data = json.load(f)

# Handle dictionary structure
if isinstance(data, dict):
    if "AAPL" in data:
        data["AAPL"]["resistance_call"] = 331.70
        data["AAPL"]["target"] = 331.70
        print(f"[✓] AAPL target level adjusted to $331.70")
    else:
        print("[!] AAPL key not found in JSON dictionary.")
elif isinstance(data, list):
    for item in data:
        if isinstance(item, dict) and item.get("ticker") == "AAPL":
            item["resistance_call"] = 331.70
            item["target"] = 331.70
            print(f"[✓] AAPL target level adjusted to $331.70")

with open(levels_file, "w") as f:
    json.dump(data, f, indent=2)

print("[✓] trading_levels.json updated successfully.")
