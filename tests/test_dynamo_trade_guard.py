import os
import sys
import unittest
from unittest.mock import patch, MagicMock

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

import boto3
from src.LiveBot import execute_order

class TestDynamoTradeGuard(unittest.TestCase):

    @patch('src.LiveBot.boto3.resource')
    def test_execute_order_blocked_when_dynamo_active_exists(self, mock_boto_resource):
        """Verify execute_order rejects new entries when DynamoDB has an ACTIVE trade."""
        mock_dynamo = MagicMock()
        mock_table = MagicMock()
        mock_boto_resource.return_value = mock_dynamo
        mock_dynamo.Table.return_value = mock_table

        # Mock DynamoDB returning 1 active item
        mock_table.scan.return_value = {'Count': 1, 'Items': [{'ticker': 'PLTR', 'exit_status': 'ACTIVE'}]}

        result = execute_order('PLTR', 'PLTR', 1.0, 'CALL', limit_price=155.0)

        self.assertFalse(result, "execute_order should return False when active trade exists in DynamoDB")
        mock_table.scan.assert_called_once()

    @patch('src.LiveBot.fetch_occ_option_symbol')
    @patch('src.LiveBot.get_live_quote')
    @patch('src.LiveBot.get_available_settled_cash')
    @patch('src.LiveBot.boto3.resource')
    def test_execute_order_passes_when_dynamo_has_no_active(
        self, mock_boto_resource, mock_cash, mock_quote, mock_occ
    ):
        """Verify execute_order proceeds when DynamoDB returns 0 ACTIVE trades."""
        mock_dynamo = MagicMock()
        mock_table = MagicMock()
        mock_boto_resource.return_value = mock_dynamo
        mock_dynamo.Table.return_value = mock_table

        # Mock DynamoDB scan returning empty active trades
        mock_table.scan.return_value = {'Count': 0, 'Items': []}

        mock_cash.return_value = 5000.0
        mock_quote.return_value = {'ask': 1.50, 'bid': 1.45, 'last': 1.50}
        mock_occ.return_value = 'NVDA260806C00200000'

        with patch('src.LiveBot.requests.post') as mock_post, \
             patch('src.LiveBot.get_order_status', return_value='filled'):
            
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'order': {'id': 12345}}

            result = execute_order('NVDA', 'NVDA', 1.0, 'CALL', limit_price=200.0)

            self.assertTrue(result, "execute_order should proceed when no ACTIVE trades exist in DynamoDB")

if __name__ == '__main__':
    unittest.main()
