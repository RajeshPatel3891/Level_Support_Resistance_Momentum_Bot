#!/usr/bin/env python3
"""
HARM.AI // PIPELINE PROXIMITY SYNC & PRE-FLIGHT GUARDRAIL TEST
===============================================================================
Verifies that all 3 proximity pipeline modules:
  1. src/sync_guardrail_levels.py
  2. src/sync_market_data.py
  3. dashboard_server.py
contain 'get_dynamic_proximity_threshold' and return identical price tier values.
"""

import os
import sys
import unittest

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

class TestProximitySync(unittest.TestCase):

    def test_1_proximity_function_presence(self):
        """Ensures get_dynamic_proximity_threshold is present in all 3 pipeline files."""
        print("\n=================================================================")
        print("🔍 [TEST 1/2] CHECKING PROXIMITY FUNCTION PRESENCE ACROSS PIPELINE")
        print("=================================================================")
        
        target_files = [
            ("Base Harvester", os.path.join(PARENT_DIR, 'src', 'sync_guardrail_levels.py')),
            ("Live Streamer",  os.path.join(PARENT_DIR, 'src', 'sync_market_data.py')),
            ("Dashboard Server", os.path.join(PARENT_DIR, 'dashboard_server.py'))
        ]

        for label, file_path in target_files:
            file_name = os.path.basename(file_path)
            self.assertTrue(os.path.exists(file_path), f"Critical file missing: {file_name}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            has_fn = "def get_dynamic_proximity_threshold" in content
            status = "✓ SYNCED" if has_fn else "❌ MISSING"
            print(f"[*] [{label}] {file_name:<30} -> {status}")

            self.assertTrue(
                has_fn,
                f"❌ PIPELINE DESYNC DETECTED: 'get_dynamic_proximity_threshold' is missing from {file_name}!"
            )

    def test_2_proximity_threshold_value_parity(self):
        """Verifies that all 3 modules return identical outputs across all price tiers."""
        print("\n=================================================================")
        print("🎯 [TEST 2/2] VERIFYING PRICE TIER THRESHOLD PARITY ACROSS MODULES")
        print("=================================================================")

        from src.sync_guardrail_levels import get_dynamic_proximity_threshold as t1
        from src.sync_market_data import get_dynamic_proximity_threshold as t2
        from dashboard_server import get_dynamic_proximity_threshold as t3

        # Test Matrix: (Spot Price, Expected Threshold Ratio, Tier Label)
        test_cases = [
            (550.0, 0.0025, "High-Dollar Assets ($SPY, $NVDA, $QQQ) -> 0.25%"),
            (45.0,  0.0035, "Mid-Tier Assets ($BAC, $UBER)        -> 0.35%"),
            (12.0,  0.0060, "Sub-$30 Assets ($SNAP, $F, $SOFI)     -> 0.60%"),
        ]

        for price, expected, tier_desc in test_cases:
            val1 = t1(price)
            val2 = t2(price)
            val3 = t3(price)

            print(f"[*] Testing Spot ${price:.2f} | {tier_desc}")
            print(f"    -> sync_guardrail_levels : {val1*100:.2f}%")
            print(f"    -> sync_market_data      : {val2*100:.2f}%")
            print(f"    -> dashboard_server      : {val3*100:.2f}%")

            # Cross-module parity assertions
            self.assertEqual(val1, expected, f"sync_guardrail_levels derived wrong threshold for ${price}")
            self.assertEqual(val2, expected, f"sync_market_data derived wrong threshold for ${price}")
            self.assertEqual(val3, expected, f"dashboard_server derived wrong threshold for ${price}")

            self.assertEqual(val1, val2, f"Desync between sync_guardrail_levels and sync_market_data at ${price}")
            self.assertEqual(val2, val3, f"Desync between sync_market_data and dashboard_server at ${price}")
            
            print(f"    [✓ PARITY ALIGNED] All 3 modules match exact {expected*100:.2f}% threshold!\n")

        print("=================================================================")
        print("🚀 ALL 3 PROXIMITY PIPELINE MODULES ARE 100% SYNCED AND ALIGNED!")
        print("=================================================================")

if __name__ == '__main__':
    unittest.main()
