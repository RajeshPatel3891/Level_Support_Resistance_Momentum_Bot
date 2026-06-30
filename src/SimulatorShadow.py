import json, sys
from LiveBot import on_message, MASTER_DATA

def run_suite():
    print("--- Starting Dynamic Level/Trend Suite ---", file=sys.stderr)
    for ticker, data in MASTER_DATA["levels"].items():
        macro = data.get("algo_macro", {})
        support = macro.get("support", [0])[0]
        resistance = macro.get("resistance", [9999])[0]
        
        # Test 1: Proximity Trigger (Support + 1.0)
        if support > 0:
            test_price = support + 1.0
            print(f"TESTING: {ticker} Proximity (Price: {test_price})", file=sys.stderr)
            on_message(None, json.dumps([{"ev": "T", "sym": ticker, "p": test_price, "v": 200000}]))
            
        # Test 2: Execution Trigger (Support)
        print(f"TESTING: {ticker} Bounce (Price: {support})", file=sys.stderr)
        on_message(None, json.dumps([{"ev": "T", "sym": ticker, "p": support, "v": 200000}]))

if __name__ == "__main__":
    run_suite()
