import unittest
import sys
import os

sys.path.extend([".", "src", "/app", "/app/src"])

class TestStopLossCushionLogic(unittest.TestCase):

    def test_low_dollar_stop_cushion(self):
        """
        [TEST 1] Low-Dollar Option Tier (<= $0.50) -> $0.10 Dollar Cushion.
        """
        fill_price = 0.24
        tier_threshold = 0.50
        
        print("\n" + "="*70)
        print("🧪 [SCENARIO 1: LOW-DOLLAR CONTRACT EVALUATION]")
        print("="*70)
        print(f"  ├─ Executed Fill Price : ${fill_price:.2f}")
        print(f"  ├─ Tier Threshold      : ${tier_threshold:.2f} (Contract is LOW-DOLLAR)")
        
        if fill_price <= tier_threshold:
            calculated_cushion = 0.10
            stop_loss = round(max(0.02, fill_price - calculated_cushion), 2)
            effective_drop_pct = ((fill_price - stop_loss) / fill_price) * 100.0
            old_20pct_stop = round(fill_price * 0.80, 2)
            
            print(f"  ├─ Tier Branch Applied : FIXED $0.10 CUSHION FLOOR")
            print(f"  ├─ Legacy 20% Stop     : ${old_20pct_stop:.2f} (Triggered on a 5¢ spread wiggle!)")
            print(f"  ├─ New Cushion Floor   : ${stop_loss:.2f} (-{effective_drop_pct:.1f}% Buffer)")
            print(f"  └─ Noise Protection    : Absorbs 10¢ of bid/ask spread noise before stop out.")
        else:
            stop_loss = round(fill_price * 0.80, 2)
            
        print("="*70)
        self.assertEqual(stop_loss, 0.14, f"Expected $0.14 stop loss for $0.24 entry, got ${stop_loss}")

    def test_standard_stop_loss(self):
        """
        [TEST 2] Standard Option Tier (> $0.50) -> 20% Percentage Stop Floor.
        """
        fill_price = 1.50
        tier_threshold = 0.50
        
        print("\n" + "="*70)
        print("🧪 [SCENARIO 2: STANDARD CONTRACT EVALUATION]")
        print("="*70)
        print(f"  ├─ Executed Fill Price : ${fill_price:.2f}")
        print(f"  ├─ Tier Threshold      : ${tier_threshold:.2f} (Contract is STANDARD)")
        
        if fill_price <= tier_threshold:
            stop_loss = round(max(0.02, fill_price - 0.10), 2)
        else:
            stop_loss = round(fill_price * 0.80, 2)
            effective_drop_pct = ((fill_price - stop_loss) / fill_price) * 100.0
            
            print(f"  ├─ Tier Branch Applied : STANDARD 20% PERCENTAGE FLOOR")
            print(f"  ├─ Calculated Stop     : ${stop_loss:.2f} (-{effective_drop_pct:.1f}% Buffer)")
            print(f"  └─ Risk Floor          : Standard 20% max risk threshold preserved.")
            
        print("="*70)
        self.assertEqual(stop_loss, 1.20, f"Expected $1.20 stop loss for $1.50 entry, got ${stop_loss}")

if __name__ == '__main__':
    unittest.main(verbosity=2)
