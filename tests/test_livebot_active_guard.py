#!/usr/bin/env python3
"""
HARM.AI // LIVE BOT ACTIVE GUARD UNIT TESTS
===============================================================================
Verifies that active position guards prevent duplicate trade injections
and allow entries when no active trades exist.
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestLiveBotActiveGuard(unittest.TestCase):

    @patch('src.smart_cso_injector.boto3.resource')
    @patch('src.smart_cso_injector.sqlite3.connect')
    def test_execute_order_blocked_if_active_trade_exists(self, mock_sql, mock_boto):
        """Verify check_active_position_exists returns True when DynamoDB has ACTIVE position."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [{'ticker': 'PLTR', 'exit_status': 'ACTIVE'}]}
        mock_boto.return_value.Table.return_value = mock_table

        from src.smart_cso_injector import check_active_position_exists
        has_active = check_active_position_exists('PLTR')
        self.assertTrue(has_active, "Guard must return True when ACTIVE position exists.")

    @patch('src.smart_cso_injector.boto3.resource')
    @patch('src.smart_cso_injector.sqlite3.connect')
    def test_execute_order_passes_guard_if_no_active_trade(self, mock_sql, mock_boto):
        """Verify check_active_position_exists returns False when no ACTIVE position exists."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': []}  # Clear active trades
        mock_boto.return_value.Table.return_value = mock_table

        from src.smart_cso_injector import check_active_position_exists
        has_active = check_active_position_exists('NVDA')
        self.assertFalse(has_active, "Guard must return False when no ACTIVE position exists.")

if __name__ == '__main__':
    unittest.main()
