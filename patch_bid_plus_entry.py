import re

file_path = "./src/smart_cso_injector.py"

with open(file_path, "r") as f:
    code = f.read()

# Function to calculate Bid-Plus limit price
bid_plus_pricer = """
def calculate_bid_plus_price(bid, ask, discount_factor=0.25):
    '''
    Calculates a limit buy price close to the Bid.
    discount_factor=0.25 places the limit order 25% above Bid (75% below Ask).
    '''
    bid_f = float(bid or 0.0)
    ask_f = float(ask or 0.0)
    if bid_f <= 0 or ask_f <= 0:
        return ask_f
    spread = ask_f - bid_f
    # Target price 25% into the spread above Bid
    target_price = round(bid_f + (spread * discount_factor), 2)
    # Ensure target price is at least bid + $0.01 if spread allows
    if target_price == bid_f and spread >= 0.02:
        target_price = round(bid_f + 0.01, 2)
    return target_price
"""

if "def calculate_bid_plus_price" not in code:
    code = bid_plus_pricer + "\n" + code

# Replace direct 'price = ask' or 'price = float(ask)' with Bid-Plus calculation
if "calculate_bid_plus_price" not in code:
    code = re.sub(
        r'price\s*=\s*(?:float\(ask\)|ask)',
        'price = calculate_bid_plus_price(bid, ask, discount_factor=0.25)',
        code
    )
    with open(file_path, "w") as f:
        f.write(code)
    print(f"[✓] Successfully injected Bid-Plus Limit Order pricing into {file_path}!")
else:
    print(f"[✓] {file_path} is already using Bid-Plus pricing.")
