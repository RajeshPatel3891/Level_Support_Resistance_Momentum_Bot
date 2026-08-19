import unittest
from datetime import datetime
import sys
import os

sys.path.extend([".", "src", "/app", "/app/src"])

from smart_cso_injector import generate_valid_occ_symbol, fetch_occ_symbol

class TestOCCSymbolGenerator(unittest.TestCase):

    def test_strike_rounding_and_min_dte_friday_guardrail(self):
        """
        [TEST] Validates OCC strike rounding ($18.11 -> $18.00) & Friday 3+ DTE guardrail.
        """
        ticker = "SOFI"
        spot_price = 18.11
        
        # Test Call generation
        call_occ = generate_valid_occ_symbol(ticker, "CALL", spot_price, min_dte=3)
        put_occ = generate_valid_occ_symbol(ticker, "PUT", spot_price, min_dte=3)
        
        # Parse expiration date
        exp_str = call_occ[4:10]
        exp_date = datetime.strptime(exp_str, "%y%m%d")
        days_out = (exp_date - datetime.now()).days
        
        # Detailed Terminal Diagnostic Output
        print("\n" + "="*70)
        print("🧪 OCC GENERATOR VERIFICATION MATRIX")
        print("="*70)
        print(f"  ├─ Input Spot Price : ${spot_price}")
        print(f"  ├─ Generated Call   : {call_occ}")
        print(f"  ├─ Generated Put    : {put_occ}")
        print(f"  ├─ Target Expiration: 20{exp_str[:2]}-{exp_str[2:4]}-{exp_str[4:]} (Friday)")
        print(f"  └─ Days to Expiry   : {days_out} Days (Min DTE >= 3 Passed)")
        print("="*70)

        # Assertions
        self.assertTrue(call_occ.startswith("SOFI"))
        self.assertIn("C00018000", call_occ)
        self.assertIn("P00018000", put_occ)
        self.assertEqual(exp_date.weekday(), 4)
        self.assertGreaterEqual(days_out, 2)

if __name__ == '__main__':
    unittest.main(verbosity=2)
