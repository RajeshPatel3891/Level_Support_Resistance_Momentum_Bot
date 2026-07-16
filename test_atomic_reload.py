import json
import time
from src.LiveBot import update_trading_levels_atomic

# 1. Load current levels
with open('trading_levels.json', 'r') as f:
    levels = json.load(f)

# 2. Modify a value (e.g., change a tactical support level)
print("Modifying trading_levels.json...")
levels["levels"]["MSFT"]["algo_macro"]["support"] = [375.0]

# 3. Perform atomic update
update_trading_levels_atomic(levels)

print("Update pushed. Check LiveBot logs for 'Detected change' message.")
