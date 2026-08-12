import unittest
from unittest.mock import patch, MagicMock
import live_gsg_guard

class TestLiveGSGGuard(unittest.TestCase):
    
    @patch('live_gsg_guard.requests.get')
    def test_fetch_tradier_quote_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'quotes': {
                'quote': {'bid': '0.50', 'ask': '0.60', 'last': '0.55'}
            }
        }
        mock_get.return_value = mock_response
        
        quote = live_gsg_guard.fetch_tradier_quote('RIVN260814C00016000')
        self.assertEqual(quote, 0.55)

    def test_pnl_gsg_threshold_calculation(self):
        entry_price = 0.41
        shares = 10.0
        live_mark = 0.55
        
        dollar_pnl = round((live_mark - entry_price) * 100.0 * shares, 2)
        self.assertGreaterEqual(dollar_pnl, 1.00)
        
        # Verify ratchet stop calculation
        new_sl = round(entry_price + 0.01, 2)
        self.assertEqual(new_sl, 0.42)

if __name__ == '__main__':
    unittest.main()
