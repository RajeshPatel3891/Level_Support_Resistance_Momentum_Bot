#!/usr/bin/env python3
"""
HARM.AI // FULL PIPELINE INTEGRATION & REVENUE CHAIN UNIT TEST
===============================================================================
Validates end-to-end execution readiness across:
1. GemmaEX Output Schema Alignment (24 Matrix Tickers)
2. S3 & Local trading_levels.json Ingestion Integrity
3. sync_market_data Execution, Price Hydration & Arming State Logic
4. Dynamic Guardrail Support/Resistance Target Calculation
5. Playbook Readiness & Trigger Bounds Verification
"""

import os
import sys
import json
import unittest

# Pathing setup
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from src.level_loader import load_trading_levels
from src.sync_market_data import sync as run_market_sync

REQUIRED_TICKERS = [
    "SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "AMZN", "GOOGL", "AMD", 
    "META", "NFLX", "PLTR", "SOFI", "F", "AAL", "INTC", "RIVN", "HOOD", 
    "BAC", "SNAP", "MARA", "CCL", "UBER", "NKE"
]

class TestRevenuePipelineChain(unittest.TestCase):

    def test_1_level_loader_s3_integrity(self):
        """Link 1: Verify S3 & Local trading_levels ingestion and enrichment."""
        print("\n[*] [LINK 1/5] Validating S3 & Local trading_levels.json schema...")
        levels = load_trading_levels(force_refresh=True)
        self.assertTrue(bool(levels), "CRITICAL: trading_levels payload is empty!")
        
        for ticker in REQUIRED_TICKERS:
            self.assertIn(ticker, levels, f"CRITICAL: Required ticker {ticker} missing from trading_levels!")
            val = levels[ticker]
            self.assertIn("spot", val, f"{ticker} missing 'spot' price!")
            self.assertIn("call_target", val, f"{ticker} missing 'call_target'!")
            self.assertIn("put_target", val, f"{ticker} missing 'put_target'!")
            self.assertIn("zone_pct", val, f"{ticker} missing enriched 'zone_pct'!")
            self.assertIn("mttp_minutes", val, f"{ticker} missing enriched 'mttp_minutes'!")

    def test_2_sync_market_data_execution(self):
        """Link 2: Execute sync_market_data and verify live quote & VWAP hydration."""
        print("[*] [LINK 2/5] Testing sync_market_data live price & VWAP hydration...")
        try:
            run_market_sync()
        except Exception as e:
            self.fail(f"CRITICAL: sync_market_data execution raised an exception: {e}")

        levels = load_trading_levels(force_refresh=True)
        for ticker in REQUIRED_TICKERS:
            val = levels[ticker]
            spot = val.get("spot", 0.0)
            vwap = val.get("vwap", 0.0)
            self.assertGreater(spot, 0.0, f"CRITICAL: {ticker} has zero/invalid spot price ({spot})!")
            self.assertGreater(vwap, 0.0, f"CRITICAL: {ticker} has zero/invalid VWAP ({vwap})!")

    def test_3_guardrail_zone_recalculation(self):
        """Link 3: Verify support/resistance zones and legacy schema mappings."""
        print("[*] [LINK 3/5] Checking Guardrail support/resistance zone calculations...")
        levels = load_trading_levels(force_refresh=True)
        for ticker in REQUIRED_TICKERS:
            val = levels[ticker]
            sup = val.get("support_zone", [])
            res = val.get("resistance_zone", [])
            
            self.assertEqual(len(sup), 2, f"CRITICAL: {ticker} support_zone must contain 2 elements!")
            self.assertEqual(len(res), 2, f"CRITICAL: {ticker} resistance_zone must contain 2 elements!")
            self.assertLessEqual(sup[0], sup[1], f"CRITICAL: {ticker} support bounds inverted: {sup}")
            self.assertLessEqual(res[0], res[1], f"CRITICAL: {ticker} resistance bounds inverted: {res}")
            
            # Verify Legacy schema backwards compatibility for playbooks
            self.assertIn("support_a", val, f"{ticker} missing 'support_a' legacy field!")
            self.assertIn("resistance_a", val, f"{ticker} missing 'resistance_a' legacy field!")

    def test_4_arming_state_logic(self):
        """Link 4: Verify dynamic execution_armed evaluation."""
        print("[*] [LINK 4/5] Evaluating dynamic execution arming state logic...")
        levels = load_trading_levels(force_refresh=True)
        armed_count = 0
        for ticker in REQUIRED_TICKERS:
            val = levels[ticker]
            self.assertIn("execution_armed", val, f"{ticker} missing 'execution_armed' flag!")
            self.assertIn("status", val, f"{ticker} missing 'status' label!")
            if val["execution_armed"]:
                armed_count += 1

        print(f"    [i] Active ARMED tickers ready for playbook execution: {armed_count}/{len(REQUIRED_TICKERS)}")

    def test_5_playbook_trigger_compatibility(self):
        """Link 5: Ensure playbook schema dependencies match trading_levels structure."""
        print("[*] [LINK 5/5] Verifying Playbook schema compatibility...")
        levels = load_trading_levels(force_refresh=True)
        for ticker in REQUIRED_TICKERS:
            val = levels[ticker]
            spot = val["spot"]
            call_target = val["call_target"]
            put_target = val["put_target"]
            
            # Ensure target drift is within trading bounds
            self.assertGreater(call_target, spot * 0.90, f"{ticker} call_target unrealistic vs spot!")
            self.assertLess(put_target, spot * 1.10, f"{ticker} put_target unrealistic vs spot!")

if __name__ == "__main__":
    unittest.main()
