import unittest
from unittest.mock import patch, MagicMock
import os
import sys

sys.path.extend(['.', 'src'])

from src.gex_exit_monitor import execute_tradier_close, synchronize_dynamo_with_tradier

class TestOrderAndDedupSafety(unittest.TestCase):

    def setUp(self):
        os.environ['TRADIER_TOKEN'] = 'mock_test_token'
        os.environ['TRADIER_ACCOUNT_ID'] = '6YB87601'

    @patch('requests.post')
    def test_execute_tradier_close_payload_structure(self, mock_post):
        """Verify order payload includes root symbol and OCC option symbol accurately."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'order': {'id': 123456, 'status': 'ok'}}
        mock_post.return_value = mock_response

        occ_symbol = 'UBER260821C00079000'
        ticker = 'UBER'
        shares = 1
        base_url = 'https://api.tradier.com/v1'

        result = execute_tradier_close(occ_symbol, ticker, shares, base_url)

        self.assertTrue(result)
        mock_post.assert_called_once()
        
        args, kwargs = mock_post.call_args
        payload = kwargs.get('data', {})

        self.assertEqual(payload.get('class'), 'option')
        self.assertEqual(payload.get('symbol'), 'UBER')
        self.assertEqual(payload.get('option_symbol'), 'UBER260821C00079000')
        self.assertEqual(payload.get('side'), 'sell_to_close')
        self.assertEqual(payload.get('quantity'), '1')

    @patch('requests.post')
    def test_execute_tradier_close_rejection_returns_false(self, mock_post):
        """Verify HTTP errors or API rejection responses return False."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        result = execute_tradier_close('AAL260821C00012000', 'AAL', 1, 'https://api.tradier.com/v1')
        self.assertFalse(result)

    @patch('boto3.resource')
    @patch('requests.get')
    def test_synchronize_dynamo_uses_deterministic_trade_id(self, mock_get, mock_boto):
        """Verify rehydration uses trade_ instead of rehydrated_ to prevent duplicates."""
        mock_tradier_res = MagicMock()
        mock_tradier_res.status_code = 200
        mock_tradier_res.json.return_value = {
            'positions': {
                'position': [
                    {'symbol': 'SOFI260821C00015500', 'quantity': 1, 'cost_basis': 243.0}
                ]
            }
        }
        mock_get.return_value = mock_tradier_res

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': []}
        mock_dynamo = MagicMock()
        mock_dynamo.Table.return_value = mock_table
        mock_boto.return_value = mock_dynamo

        synchronize_dynamo_with_tradier()

        mock_table.put_item.assert_called_once()
        put_kwargs = mock_table.put_item.call_args[1]
        item = put_kwargs['Item']

        self.assertEqual(item['trade_id'], 'trade_sofi260821c00015500')
        self.assertFalse(item['trade_id'].startswith('rehydrated_'))

if __name__ == '__main__':
    unittest.main()
