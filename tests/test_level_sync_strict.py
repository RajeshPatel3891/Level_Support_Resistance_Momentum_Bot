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
        
        # Load levels (should hit cache or local file)
        levels_1 = load_trading_levels(force_refresh=False)
        self.assertEqual(levels_1, dummy_data)
        
        # Update with new data via write-through
        new_data = {"test_ticker": {"target": 200.0}}
        save_trading_levels(new_data)
        
        # Immediate read should reflect new data instantly due to cache invalidation
        levels_2 = load_trading_levels(force_refresh=False)
        self.assertEqual(levels_2, new_data)

if __name__ == "__main__":
    unittest.main()
