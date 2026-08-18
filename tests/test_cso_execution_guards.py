#!/usr/bin/env python3
"""
HARM.AI // SMART CSO INJECTOR EXECUTION GUARD UNIT TESTS
===============================================================================
Tests the broker rejection & ghost fill verification logic in smart_cso_injector.py
to prevent false DB registrations and orphan trade logging.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is in Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.smart_cso_injector import (
    execute_adaptive_micro_scalp_order,
    execute_strict_tradier_order
)

class TestSmartCSOExecutionGuards(unittest.TestCase):

    @patch('src.smart_cso_injector.TRADIER_TOKEN', 'mock_token')
    @patch('src.smart_cso_injector.TRADIER_ACCOUNT_ID', 'mock_account')
    @patch('src.smart_cso_injector.get_live_quote')
    @patch('requests.post')
    @patch('requests.get')
    def test_rejection_aborts_without_db_write(self, mock_get, mock_post, mock_quote):
        """Verify that an order REJECTED by Tradier backoffice returns False immediately."""
        mock_quote.return_value = {'bid': 0.35, 'ask': 0.37}

        # Mock initial POST response (API Gateway returns 200 OK with order_id)
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {'order': {'id': '99901'}}
        mock_post.return_value = mock_post_resp

        # Mock subsequent GET status check returning REJECTED status
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            'order': {
                'id': '99901',
                'status': 'rejected',
                'exec_quantity': 0,
                'avg_fill_price': 0.0
            }
        }
        mock_get.return_value = mock_get_resp

        # Execute micro-scalp order
        success, fill_px, order_id = execute_adaptive_micro_scalp_order(
            'SOFI260821C00018500', 'SOFI', 'CALL', quantity=1
        )

        self.assertFalse(success, "Engine must return False when order is rejected.")
        self.assertEqual(fill_px, 0.0, "Fill price must be 0.0 on rejection.")
        self.assertEqual(order_id, "", "Order ID must be cleared on rejection.")

    @patch('src.smart_cso_injector.TRADIER_TOKEN', 'mock_token')
    @patch('src.smart_cso_injector.TRADIER_ACCOUNT_ID', 'mock_account')
    @patch('src.smart_cso_injector.get_live_quote')
    @patch('requests.post')
    @patch('requests.get')
    def test_ghost_fill_zero_exec_qty_fails(self, mock_get, mock_post, mock_quote):
        """Verify that status=='filled' with exec_quantity=0 is caught as a ghost fill."""
        mock_quote.return_value = {'bid': 0.35, 'ask': 0.37}

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {'order': {'id': '99902'}}
        mock_post.return_value = mock_post_resp

        # Status claims 'filled' but executed quantity is 0
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            'order': {
                'id': '99902',
                'status': 'filled',
                'exec_quantity': 0,
                'avg_fill_price': 0.36
            }
        }
        mock_get.return_value = mock_get_resp

        success, fill_px, order_id = execute_adaptive_micro_scalp_order(
            'SOFI260821C00018500', 'SOFI', 'CALL', quantity=1
        )

        self.assertFalse(success, "Ghost fills (exec_quantity=0) must be rejected.")
        self.assertEqual(fill_px, 0.0)

    @patch('src.smart_cso_injector.TRADIER_TOKEN', 'mock_token')
    @patch('src.smart_cso_injector.TRADIER_ACCOUNT_ID', 'mock_account')
    @patch('src.smart_cso_injector.get_live_quote')
    @patch('requests.post')
    @patch('requests.get')
    def test_valid_fill_succeeds(self, mock_get, mock_post, mock_quote):
        """Verify that a legitimate exchange fill (exec_quantity > 0) passes successfully."""
        mock_quote.return_value = {'bid': 0.35, 'ask': 0.37}

        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {'order': {'id': '99903'}}
        mock_post.return_value = mock_post_resp

        # Valid exchange receipt
        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            'order': {
                'id': '99903',
                'status': 'filled',
                'exec_quantity': 1,
                'quantity': 1,
                'avg_fill_price': 0.36
            }
        }
        mock_get.return_value = mock_get_resp

        success, fill_px, order_id = execute_adaptive_micro_scalp_order(
            'SOFI260821C00018500', 'SOFI', 'CALL', quantity=1
        )

        self.assertTrue(success, "Valid fills must pass.")
        self.assertEqual(fill_px, 0.36, "Fill price must match execution receipt.")
        self.assertEqual(order_id, '99903', "Order ID must be preserved for DB logging.")

if __name__ == '__main__':
    unittest.main()
