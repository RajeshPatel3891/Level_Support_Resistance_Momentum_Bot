import unittest
import time
import os
import json
from src.level_loader import load_trading_levels, save_trading_levels

class TestLevelSyncStrict(unittest.TestCase):
    
    def test_write_through_cache_invalidation(self):
        """Verify that saving levels immediately updates cache without polling."""
        dummy_data = {"test_ticker": {"target": 150.0}}
        save_trading_levels(dummy_data)
        
        # Load levels (returns write-through enriched payload)
        levels_1 = load_trading_levels(force_refresh=False)
        self.assertIn("test_ticker", levels_1)
        self.assertEqual(levels_1["test_ticker"]["target"], 150.0)
        self.assertEqual(levels_1["test_ticker"]["beta"], "MID")
        
        # Update with new data via write-through
        new_data = {"test_ticker": {"target": 200.0}}
        save_trading_levels(new_data)
        
        # Immediate read should reflect new target instantly due to cache invalidation
        levels_2 = load_trading_levels(force_refresh=False)
        self.assertIn("test_ticker", levels_2)
        self.assertEqual(levels_2["test_ticker"]["target"], 200.0)

if __name__ == "__main__":
    unittest.main()
