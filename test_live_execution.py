import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Ensure internal module pathways are aligned
sys.path.append(os.getcwd())

from src.LiveBot import execute_order

def run_integration_test():
    print("=====================================================================")
    print("🛰️  HARM.AI // LIVE TRADIER SANDBOX INTEGRATION TEST")
    print("=====================================================================")
    
    # 1. Define real test inputs (Underlying Symbol, OCC Option Symbol, Qty, Side)
    test_symbol = "PLTR"
    test_option_ticker = "PLTR260717C00030000" 
    test_qty = 1
    test_side = "buy_to_open"
    
    print(f"[*] Dispatching live test to Tradier Sandbox...")
    print(f"[*] Account ID: {os.getenv('TRADIER_ACCOUNT_ID')}")
    print(f"[*] Option Symbol Target: {test_option_ticker}")
    print("-" * 69)
    
    # 2. Fire the newly upgraded execute_order function!
    success = execute_order(test_symbol, test_option_ticker, test_qty, test_side)
    
    if success:
        print("-" * 69)
        print("[✓] TEST PASSED: order accepted by Tradier Sandbox API!")
        print("[*] Please run 'view_pipeline.py' to see the active order.")
    else:
        print("-" * 69)
        print("[-] TEST FAILED: Verify your TRADIER_TOKEN and TRADIER_ACCOUNT_ID.")

if __name__ == "__main__":
    run_integration_test()
