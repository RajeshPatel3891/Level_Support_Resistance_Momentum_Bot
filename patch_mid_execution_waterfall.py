import re

file_path = "./src/smart_cso_injector.py"

with open(file_path, "r") as f:
    code = f.read()

execution_logic = """
def execute_smart_order(tradier_client, account_id, symbol, option_symbol, bid, ask, quantity=1):
    '''
    Stage 1: Attempt Limit order fill at MID price.
    Stage 2: Fallback to ASK if unfilled after 3s and spread <= 1.0%.
    '''
    import time
    bid_f = float(bid or 0.0)
    ask_f = float(ask or 0.0)
    if ask_f <= 0 or bid_f <= 0:
        print(f"[!] Invalid quote for {option_symbol}. Aborting.")
        return None

    mid_price = round((bid_f + ask_f) / 2.0, 2)
    spread_pct = (ask_f - bid_f) / ask_f

    # Step 1: Submit Limit Order at MID
    print(f"[*] [STAGE 1] Submitting Limit Order at MID: ${mid_price:.2f} (Bid: ${bid_f:.2f} / Ask: ${ask_f:.2f})")
    order_id = tradier_client.place_option_order(
        account_id, symbol, option_symbol, side='buy_to_open', 
        quantity=quantity, order_type='limit', price=mid_price
    )
    
    time.sleep(3)  # Wait 3s for Mid-fill
    
    status = tradier_client.get_order_status(account_id, order_id)
    if status == 'filled':
        print(f"[✓] [MID FILL SUCCESS] Filled {option_symbol} at ${mid_price:.2f}!")
        return {'order_id': order_id, 'fill_price': mid_price, 'type': 'MID_FILL'}

    # Step 2: Fallback check
    if spread_pct <= 0.01:
        print(f"[*] [STAGE 2] Mid unfilled. Spread is tight ({spread_pct*100.0:.2f}% <= 1.0%). Escalating to ASK (${ask_f:.2f})...")
        tradier_client.modify_order(account_id, order_id, price=ask_f)
        time.sleep(1)
        return {'order_id': order_id, 'fill_price': ask_f, 'type': 'ASK_FALLBACK'}
    else:
        print(f"[⛔ SPREAD GUARD] Canceling order {order_id}. Mid unfilled & spread ({spread_pct*100.0:.2f}%) > 1.0%.")
        tradier_client.cancel_order(account_id, order_id)
        return None
"""

if "def execute_smart_order" not in code:
    code = execution_logic + "\n" + code
    with open(file_path, "w") as f:
        f.write(code)
    print(f"[✓] Injected Mid-to-Ask Execution Waterfall into {file_path}!")
else:
    print(f"[✓] Execution waterfall already installed in {file_path}.")
