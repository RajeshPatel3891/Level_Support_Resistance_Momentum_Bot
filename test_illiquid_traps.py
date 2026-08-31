#!/usr/bin/env python3
"""
HARM.AI // UNIT TEST SUITE FOR ILLIQUID TRAP GUARDS
===============================================================================
"""

import unittest
from src.smart_cso_injector import validate_option_liquidity

class TestIlliquidTrapGuards(unittest.TestCase):

    def test_zero_bid_trap_rejected(self):
        """Reject contracts with zero or $0.01 bid."""
        quote = {"bid": 0.01, "ask": 0.15, "open_interest": 500, "volume": 100}
        passed, reason = validate_option_liquidity(quote)
        self.assertFalse(passed)
        self.assertTrue("is $0.01 or zero" in reason or "Illiquid Trap" in reason)

    def test_wide_spread_rejected(self):
        """Reject contracts with wide bid-ask spread (> 8% or > $0.03 for cheap contracts)."""
        quote = {"bid": 0.50, "ask": 0.65, "open_interest": 500, "volume": 100}
        passed, reason = validate_option_liquidity(quote)
        self.assertFalse(passed)
        self.assertTrue("exceeds 8% cap" in reason or "exceeds cap" in reason or "exceeds $0.03" in reason)

    def test_low_volume_oi_rejected(self):
        """Reject contracts with low open interest or volume."""
        quote = {"bid": 1.00, "ask": 1.05, "open_interest": 10, "volume": 5}
        passed, reason = validate_option_liquidity(quote)
        self.assertFalse(passed)
        self.assertIn("Low Liquidity", reason)

    def test_liquid_contract_passed(self):
        """Pass high quality liquid contracts."""
        quote = {"bid": 1.00, "ask": 1.05, "open_interest": 1500, "volume": 500}
        passed, reason = validate_option_liquidity(quote)
        self.assertTrue(passed)
        self.assertEqual(reason, "Passed")

if __name__ == "__main__":
    unittest.main()
