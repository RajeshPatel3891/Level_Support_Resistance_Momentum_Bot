#!/usr/bin/env python3
"""
HARM.AI // PREDICTIVE CSO TICK PLAYBACK SIMULATOR
===============================================================================
Replays intraday tick streams against smart_cso_injector.py to verify:
1. Armed Zone Filtering (±0.3% boundary enforcement)
2. Micro-Velocity Reversal Detection (1-cent bottom/top turns)
3. 3-Tier Micro-Scalp Execution & Rejection Safeguards
"""

import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

# Force path resolution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.smart_cso_injector import check_predictive_armed_trigger, execute_adaptive_micro_scalp_order

class TestTickPlaybackHarness(unittest.TestCase):

    def setUp(self):
        self.sofi_info = {
            "spot": 18.33,
            "last_price": 18.33,
            "execution_armed": True,
            "vwap": 18.28
        }

    @patch('src.smart_cso_injector.get_live_quote')
    def test_playback_scenario_1_outside_zone_blocked(self, mock_quote):
        """PLAYBACK SCENARIO 1: Price hovering at $18.43 (0.55% above armed target). Must reject entry."""
        print("\n" + "="*60)
        print("🎬 PLAYBACK SCENARIO 1: Outside Armed Zone ($18.43 vs $18.33)")
        print("="*60)

        # Mock sequence of quotes at $18.43
        mock_quote.side_effect = [
            {'last': 18.43}, {'last': 18.43}, {'last': 18.43}
        ]

        triggered, reason = check_predictive_armed_trigger('SOFI', self.sofi_info)
        print(f"Result: Triggered={triggered} | Reason: {reason}")

        self.assertFalse(triggered)
        self.assertIn("OUTSIDE_ARMED_ZONE", reason)

    @patch('src.smart_cso_injector.get_live_quote')
    def test_playback_scenario_2_inside_zone_micro_reversal_fires(self, mock_quote):
        """PLAYBACK SCENARIO 2: Price enters zone ($18.34 -> $18.32 -> $18.33 reversal). Must trigger entry."""
        print("\n" + "="*60)
        print("🎬 PLAYBACK SCENARIO 2: Reversal Tick Inside Zone ($18.34 -> $18.32 -> $18.33)")
        print("="*60)

        # Replay sequence showing a 1-cent micro bottom turn inside ±0.3%
        mock_quote.side_effect = [
            {'last': 18.34}, # Tick 1: Dropping
            {'last': 18.32}, # Tick 2: Local low
            {'last': 18.33}  # Tick 3: First 1-cent upward reversal!
        ]

        triggered, reason = check_predictive_armed_trigger('SOFI', self.sofi_info)
        print(f"Result: Triggered={triggered} | Reason: {reason}")

        self.assertTrue(triggered)
        self.assertIn("PREDICTIVE_MICRO_BOTTOM_CONFIRMED", reason)

    @patch('src.smart_cso_injector.TRADIER_TOKEN', 'mock_token')
    @patch('src.smart_cso_injector.TRADIER_ACCOUNT_ID', 'mock_account')
    @patch('src.smart_cso_injector.get_live_quote')
    @patch('requests.post')
    @patch('requests.get')
    def test_playback_scenario_3_tier1_fill_execution(self, mock_get, mock_post, mock_quote):
        """PLAYBACK SCENARIO 3: Reversal confirmed -> Executes 3-Tier Micro-Scalp -> Fills Tier 1."""
        print("\n" + "="*60)
        print("🎬 PLAYBACK SCENARIO 3: Execution Ladder Tier 1 Fill ($0.36 Inside Bid)")
        print("="*60)

        mock_quote.return_value = {'bid': 0.35, 'ask': 0.37}

        # Mock Order Creation (200 OK)
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {'order': {'id': 'SIM_77701'}}
        mock_post.return_value = mock_post_resp

        # Mock Fill Status
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            'order': {
                'id': 'SIM_77701',
                'status': 'filled',
                'exec_quantity': 1,
                'avg_fill_price': 0.36
            }
        }
        mock_get.return_value = mock_get_resp

        success, fill_px, order_id = execute_adaptive_micro_scalp_order(
            'SOFI260821C00018500', 'SOFI', 'CALL', quantity=1
        )
        print(f"Result: Success={success} | Fill Price=${fill_px:.2f} | Order ID={order_id}")

        self.assertTrue(success)
        self.assertEqual(fill_px, 0.36)
        self.assertEqual(order_id, 'SIM_77701')

if __name__ == '__main__':
    unittest.main()
