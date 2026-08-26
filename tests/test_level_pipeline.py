from src.utils.universe import get_playbook_tickers
#!/usr/bin/env python3
"""
HARM.AI // PRE-FLIGHT FARGATE LEVEL PIPELINE UNIT TEST
===============================================================================
Fails deployment immediately if S3 levels are missing, corrupted, or un-enriched.
"""

import unittest
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from src.level_loader import load_trading_levels


TICKERS = get_playbook_tickers()
REQUIRED_KEYS = ["spot", "call_target", "put_target", "support_zone", "resistance_zone", "beta", "zone_pct", "mttp_minutes"]

class TestS3LevelPipeline(unittest.TestCase):

    def test_s3_level_ingestion_and_enrichment(self):
        print("\n[*] [UNIT TEST] Executing Cloud-First S3 Level Verification...")
        
        # 1. Force refresh from S3
        levels = load_trading_levels(force_refresh=True)
        
        # 2. Assert level dictionary is non-empty
        self.assertTrue(bool(levels), "CRITICAL: load_trading_levels() returned an empty dictionary!")
        
        # 3. Assert dummy test_ticker is not present
        self.assertNotIn("test_ticker", levels, "CRITICAL: S3 levels file still contains dummy 'test_ticker'!")
        
        # 4. Assert all required production tickers are present
        REQUIRED_TICKERS = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "AMZN", "GOOGL", "AMD", "META", "NFLX", "PLTR", "SOFI", "F", "AAL", "INTC", "RIVN", "HOOD", "BAC", "SNAP", "MARA", "CCL", "UBER", "NKE"]
        for ticker in REQUIRED_TICKERS:
            self.assertIn(ticker, levels, f"CRITICAL: Production ticker {ticker} missing from S3 levels payload!")
            
            # 5. Assert schema and enriched beta parameters exist
            ticker_data = levels[ticker]
            for key in REQUIRED_KEYS:
                self.assertIn(key, ticker_data, f"CRITICAL: {ticker} payload missing required key '{key}'!")
                
            # 6. Assert non-zero support/resistance targets
            self.assertGreater(ticker_data["spot"], 0, f"CRITICAL: {ticker} spot price is 0.00!")
            self.assertGreater(ticker_data["call_target"], 0, f"CRITICAL: {ticker} call_target is 0.00!")
            self.assertGreater(ticker_data["put_target"], 0, f"CRITICAL: {ticker} put_target is 0.00!")

        print(f"[✓] [UNIT TEST PASSED] Verified {len(levels)} production tickers in S3 with full Beta enrichment.")

if __name__ == "__main__":
    unittest.main()
