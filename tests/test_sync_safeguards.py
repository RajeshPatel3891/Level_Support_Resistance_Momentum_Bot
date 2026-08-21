import unittest
from unittest.mock import MagicMock, patch
import os
import sys

# Ensure src path is available
sys.path.extend(['.', 'src'])
import src.gex_exit_monitor as gex


class TestSyncSafeguards(unittest.TestCase):

    @patch('src.gex_exit_monitor.boto3.resource')
    @patch('src.gex_exit_monitor.requests.get')
    def test_synchronize_dynamo_normalizes_option_prices(self, mock_requests_get, mock_boto_resource):
        """Verify cost_basis ($152.00) normalizes to per-share entry price ($1.52)."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'positions': {
                'position': [{
                    'symbol': 'AAL260821C00012000',
                    'quantity': '1.0',
                    'cost_basis': '152.00',
                    'date_acquired': '2026-08-20'
                }]
            }
        }
        mock_requests_get.return_value = mock_response

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': []}
        mock_boto_resource.return_value.Table.return_value = mock_table

        gex.synchronize_dynamo_with_tradier()

        self.assertTrue(mock_table.put_item.called)
        written_item = mock_table.put_item.call_args[1]['Item']
        
        self.assertEqual(written_item['ticker'], 'AAL')
        self.assertEqual(written_item['entry_price'], '1.52')
        self.assertEqual(written_item['cost_basis'], '1.52')

    @patch('src.gex_exit_monitor.requests.post')
    def test_execute_tradier_close_failure_does_not_confirm(self, mock_requests_post):
        """Verify failed order close returns False to prevent optimistic DB writes."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'order': {'status': 'rejected', 'reason': 'Insufficient funds'}}
        mock_requests_post.return_value = mock_response

        success = gex.execute_tradier_close('SOFI260821C00015500', 'SOFI', 1, 'https://api.tradier.com/v1', max_wait_seconds=1)
        self.assertFalse(success)

    @patch('src.gex_exit_monitor.boto3.resource')
    @patch('src.gex_exit_monitor.requests.get')
    def test_reconciliation_purges_ghost_positions(self, mock_requests_get, mock_boto_resource):
        """Verify periodic reconciliation marks ghost positions as resolved."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'positions': 'null'}
        mock_requests_get.return_value = mock_response

        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [{
                'tenant_id': 'COMPANY_A_PROD',
                'trade_id': 'trade_mara260821p00011000',
                'ticker': 'MARA',
                'occ_symbol': 'MARA260821P00011000',
                'exit_status': 'ACTIVE'
            }]
        }
        mock_boto_resource.return_value.Table.return_value = mock_table

        gex.synchronize_dynamo_with_tradier()
        self.assertTrue(mock_table.update_item.called or mock_table.delete_item.called)


if __name__ == '__main__':
    unittest.main()
