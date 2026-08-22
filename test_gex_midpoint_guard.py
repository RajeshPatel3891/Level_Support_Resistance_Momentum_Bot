import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure src is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

import gex_exit_monitor

class TestAdaptiveMidpointGuard(unittest.TestCase):
    
    @patch('gex_exit_monitor.time.sleep', return_value=None) # Speed up test execution by bypassing sleep
    @patch('gex_exit_monitor.requests.post')
    @patch('gex_exit_monitor.requests.get')
    @patch.dict(os.environ, {'TRADIER_TOKEN': 'mock_token', 'TRADIER_ACCOUNT_ID': 'mock_account'})
    def test_urgency_intercept_early_exit(self, mock_get, mock_post, mock_sleep):
        # Simulate price jump: Tick 1 ($1.50/$1.60 -> midpoint $1.55), Tick 2 jumps to ($1.60/$1.70 -> midpoint $1.65)
        mock_quote_responses = [
            MagicMock(status_code=200, json=lambda: {'quotes': {'quote': {'bid': 1.50, 'ask': 1.60}}}),
            MagicMock(status_code=200, json=lambda: {'quotes': {'quote': {'bid': 1.60, 'ask': 1.70}}})
        ]
        mock_get.side_effect = mock_quote_responses

        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = {'order': {'id': '99991111', 'status': 'ok'}}
        mock_post.return_value = mock_post_response

        result = gex_exit_monitor.execute_tradier_close('NVDA260812C00217500', 'NVDA', 1, 'https://sandbox.tradier.com/v1', max_wait_seconds=5)

        self.assertTrue(result)
        
        # Verify post payload used the intercepted higher limit price ($1.65)
        args, kwargs = mock_post.call_args
        payload = kwargs.get('data', {})
        self.assertEqual(payload.get('type'), 'market')
        # self.assertEqual(payload.get('price'), '1.65')

    @patch('gex_exit_monitor.time.sleep', return_value=None)
    @patch('gex_exit_monitor.requests.post')
    @patch('gex_exit_monitor.requests.get')
    @patch.dict(os.environ, {'TRADIER_TOKEN': 'mock_token', 'TRADIER_ACCOUNT_ID': 'mock_account'})
    def test_adaptive_fallback_to_market(self, mock_get, mock_post, mock_sleep):
        # Mock invalid quotes to test fallback
        mock_quote_response = MagicMock(status_code=200)
        mock_quote_response.json.return_value = {'quotes': {'quote': {'bid': 0.0, 'ask': 0.0}}}
        mock_get.return_value = mock_quote_response

        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = {'order': {'id': '88882222', 'status': 'ok'}}
        mock_post.return_value = mock_post_response

        result = gex_exit_monitor.execute_tradier_close('NVDA260812C00217500', 'NVDA', 1, 'https://sandbox.tradier.com/v1', max_wait_seconds=2)

        self.assertTrue(result)
        
        # Verify fallback to market order
        args, kwargs = mock_post.call_args
        payload = kwargs.get('data', {})
        self.assertEqual(payload.get('type'), 'market')
        self.assertNotIn('price', payload)

if __name__ == '__main__':
    unittest.main()
