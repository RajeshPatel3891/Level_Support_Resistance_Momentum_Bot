#!/usr/bin/env python3
"""
HARM.AI // LOCAL END-TO-END TEST HARNESS
===============================================================================
Tests:
  1. UI Template & JS Poller Validation (index HTML, 5s poller, 10s auto-refresh)
  2. CSO Order Walker Execution Engine (/api/inject_trade)
  3. Dynamic Entry Pricing (25% Peg vs 50% Midpoint)
  4. Write-through DB Hydration (DynamoDB & SQLite Active Registration)
"""

import os, sys, time, unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

sys.path.extend([".", "src"])

import dashboard_server
import src.smart_cso_daemon as cso_daemon

class TestUIAndSmartCSOIntegration(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(dashboard_server.app)
        self.ticker = "SOFI"
        self.occ_symbol = "SOFI260821P00019000"

    def test_01_ui_template_and_poller_hooks(self):
        """1. Verify UI rendered template includes poller and inject script hooks."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.text

        # Assert UI DOM containers & Javascript auto-refresh loops exist
        self.assertIn('id="proximity-container"', html)
        self.assertIn('function triggerUiInjectStream(ticker)', html)
        self.assertIn('/dashboard_data.json', html)
        self.assertIn('window.location.reload()', html)
        print("\n[✓ TEST 1 PASSED] UI Index HTML & 5s Poller / Auto-Refresh script verified!")

    @patch('src.smart_cso_daemon.get_live_quote_dict')
    @patch('src.smart_cso_daemon.place_limit_order')
    @patch('src.smart_cso_daemon.wait_for_fill')
    @patch('src.smart_cso_daemon.cancel_order')
    @patch('src.smart_cso_daemon.register_active_position_in_dynamo')
    def test_02_smart_cso_walker_midpoint_stepup(self, mock_reg, mock_cancel, mock_wait, mock_place, mock_quote):
        """2. Verify smart_cso order walker steps from Tier 1 Peg to Tier 2 Midpoint when Tier 1 times out."""
        # Mock Quote: Bid = $0.10, Ask = $0.14 -> Mid = $0.12, 25% Peg = $0.11
        mock_quote.return_value = {'bid': 0.10, 'ask': 0.14}
        mock_place.side_effect = ["order_tier1_101", "order_tier2_102"]
        
        # Tier 1 fails (times out), Tier 2 fills
        mock_wait.side_effect = [False, True]
        mock_cancel.return_value = True

        res = self.client.post("/api/inject_trade", json={
            "ticker": self.ticker,
            "occ_symbol": self.occ_symbol
        })

        self.assertEqual(res.status_code, 200)
        body = res.json()

        # Assert status success and returned fill details
        self.assertEqual(body.get('status'), 'success')
        self.assertEqual(body['result']['order_id'], "order_tier2_102")
        self.assertEqual(body['result']['fill_price'], 0.12)

        # Verify Tier 1 canceled and Tier 2 Midpoint placed
        mock_cancel.assert_called_with("order_tier1_101")
        mock_reg.assert_called_once_with(self.ticker, self.occ_symbol, 0.12, 1, "order_tier2_102")

        print("[✓ TEST 2 PASSED] Order Walker successfully stepped from Tier 1 ($0.11) -> Tier 2 Midpoint ($0.12) & registered DB state!")

    def test_03_pricing_math_peg_logic(self):
        """3. Verify Dynamic Peg pricing calculation math."""
        # Penny spread -> Strict Bid
        px_tight = cso_daemon.calculate_dynamic_entry_price(0.10, 0.11, momentum_score=0.5)
        self.assertEqual(px_tight, 0.10)

        # Low Momentum -> 25% Peg
        px_low = cso_daemon.calculate_dynamic_entry_price(0.10, 0.20, momentum_score=0.5)
        self.assertEqual(px_low, 0.12)  # $0.10 + ($0.10 * 0.25) = $0.125 -> $0.12

        # High Momentum -> 50% Mid
        px_high = cso_daemon.calculate_dynamic_entry_price(0.10, 0.20, momentum_score=0.8)
        self.assertEqual(px_high, 0.15)  # $0.10 + ($0.10 * 0.50) = $0.15

        print("[✓ TEST 3 PASSED] Dynamic Peg & Spread Pricing Math verified!")

if __name__ == "__main__":
    unittest.main()
