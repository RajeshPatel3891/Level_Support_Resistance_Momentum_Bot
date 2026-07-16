import os
import sys
import json
import unittest

# Ensure the project root is in the path to import src
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.AlpacaPipeline import calculate_trade_conviction

class TestAlpacaPipeline(unittest.TestCase):
    """
    Data-driven test suite for Harmonized AI Pipeline logic.
    Injects various market scenarios to validate sentiment override rules.
    """

    def setUp(self):
        # We simulate the macro_state file before each test
        self.macro_path = os.path.join(os.path.dirname(__file__), '..', 'macro_state.json')

    def write_macro_state(self, state):
        with open(self.macro_path, 'w') as f:
            json.dump(state, f)

    def test_risk_off_liquidation_blocks_longs(self):
        # Scenario: Macro is in full liquidation
        self.write_macro_state({
            "macro_regime": "RISK_OFF_LIQUIDATION",
            "risk_bias": "RISK_OFF_LIQUIDATION",
            "operational_directive": "PROTECT CAPITAL"
        })
        
        result = calculate_trade_conviction("SPY", 540.00, "LONG")
        self.assertEqual(result['action'], "PASS")
        self.assertIn("BLOCKED BY MACRO SENTINEL", result['notes'])

    def test_normal_regime_allows_trade(self):
        # Scenario: Normal operations
        self.write_macro_state({
            "macro_regime": "NORMAL",
            "risk_bias": "NEUTRAL",
            "operational_directive": "None"
        })
        
        result = calculate_trade_conviction("SPY", 540.00, "LONG")
        self.assertEqual(result['action'], "READY")

if __name__ == '__main__':
    unittest.main()
