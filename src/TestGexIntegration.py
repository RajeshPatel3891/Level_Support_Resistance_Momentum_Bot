import sys
import os

# Ensure package paths match up
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from src.LiveBot import evaluate_ticker_risk

def run_integration_test():
    print("=" * 60)
    print("🦅 HARM.AI // GEX CORE INTEGRATION TEST ENGINE")
    print("=" * 60)
    
    # Test Case 1: Testing a known POSITIVE Gamma asset from your DB pool
    test_ticker_pos = "PLTR"
    print(f"\n[*] Triggering mock incoming stream check for: {test_ticker_pos}")
    regime_pos = evaluate_ticker_risk(test_ticker_pos)
    print(f"[✓] Engine Decision for {test_ticker_pos}: {regime_pos}")
    
    print("-" * 40)
    
    # Test Case 2: Testing a known NEGATIVE Gamma asset from your DB pool
    test_ticker_neg = "AAL"
    print(f"\n[*] Triggering mock incoming stream check for: {test_ticker_neg}")
    regime_neg = evaluate_ticker_risk(test_ticker_neg)
    print(f"[✓] Engine Decision for {test_ticker_neg}: {regime_neg}")
    print("=" * 60)

if __name__ == '__main__':
    run_integration_test()
