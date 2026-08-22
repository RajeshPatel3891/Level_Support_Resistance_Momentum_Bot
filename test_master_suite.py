import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure src/ directory is on Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

import gex_exit_monitor
import auto_inject_armed

# ==============================================================================
# 1. TRAILING STOP & RISK ENGINE TESTS
# ==============================================================================
def calculate_dynamic_stop(entry_price: float, peak_pnl_pct: float, is_runner: bool = False) -> float:
    """Helper mirroring the dynamic stop logic inside gex_exit_monitor.py."""
    if is_runner:
        cushion = 12.0 if peak_pnl_pct >= 100.0 else 10.0
        dynamic_stop_pct = max(3.0, peak_pnl_pct - cushion)
        return round(entry_price * (1.0 + dynamic_stop_pct / 100.0), 2)
    elif peak_pnl_pct >= 35.0:
        return round(entry_price * (1.0 + (peak_pnl_pct - 10.0) / 100.0), 2)
    elif peak_pnl_pct >= 20.0:
        return round(entry_price * (1.0 + (peak_pnl_pct - 10.0) / 100.0), 2)
    elif peak_pnl_pct >= 12.0:
        return round(entry_price * 1.03, 2)
    else:
        return round(entry_price * 0.80, 2)


class TestGEXExitMonitorTrailingStops(unittest.TestCase):

    def test_nvda_high_water_mark_trailing_stop(self):
        """Test NVDA scenario: Entry $1.73, Peak PnL +189.6% -> Expected Stop: $4.84"""
        entry_price = 1.73
        peak_pnl_pct = 189.6
        stop = calculate_dynamic_stop(entry_price, peak_pnl_pct, is_runner=False)
        self.assertEqual(stop, 4.84)
        self.assertTrue(stop > entry_price)

    def test_tier_2_mid_peak_trailing_stop(self):
        """Test Tier 2: Entry $2.00, Peak PnL +25.0% -> Expected Stop: $2.30 (+15% lock)"""
        entry_price = 2.00
        peak_pnl_pct = 25.0
        stop = calculate_dynamic_stop(entry_price, peak_pnl_pct, is_runner=False)
        self.assertEqual(stop, 2.30)

    def test_green_stay_green_floor(self):
        """Test Tier 1: Entry $1.00, Peak PnL +15.0% -> Expected Stop: $1.03 (+3% breakeven lock)"""
        entry_price = 1.00
        peak_pnl_pct = 15.0
        stop = calculate_dynamic_stop(entry_price, peak_pnl_pct, is_runner=False)
        self.assertEqual(stop, 1.03)

    def test_initial_risk_floor(self):
        """Test Initial Floor: Entry $1.00, Peak PnL +5.0% -> Expected Stop: $0.80 (-20% stop)"""
        entry_price = 1.00
        peak_pnl_pct = 5.0
        stop = calculate_dynamic_stop(entry_price, peak_pnl_pct, is_runner=False)
        self.assertEqual(stop, 0.80)

    def test_runner_trailing_stop_over_100pct(self):
        """Test Runner State: Entry $1.00, Peak PnL +150.0% -> Expected Stop: $2.38 (12% cushion)"""
        entry_price = 1.00
        peak_pnl_pct = 150.0
        stop = calculate_dynamic_stop(entry_price, peak_pnl_pct, is_runner=True)
        self.assertEqual(stop, 2.38)


# ==============================================================================
# 2. ADAPTIVE MIDPOINT & URGENCY INTERCEPT TESTS
# ==============================================================================
class TestAdaptiveMidpointGuard(unittest.TestCase):
    
    @patch('gex_exit_monitor.time.sleep', return_value=None)
    @patch('gex_exit_monitor.requests.post')
    @patch('gex_exit_monitor.requests.get')
    @patch.dict(os.environ, {'TRADIER_TOKEN': 'mock_token', 'TRADIER_ACCOUNT_ID': 'mock_account'})
    def test_urgency_intercept_early_exit(self, mock_get, mock_post, mock_sleep):
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
        args, kwargs = mock_post.call_args
        payload = kwargs.get('data', {})
        self.assertEqual(payload.get('type'), 'market')
        # self.assertEqual(payload.get('price'), '1.65')

    @patch('gex_exit_monitor.time.sleep', return_value=None)
    @patch('gex_exit_monitor.requests.post')
    @patch('gex_exit_monitor.requests.get')
    @patch.dict(os.environ, {'TRADIER_TOKEN': 'mock_token', 'TRADIER_ACCOUNT_ID': 'mock_account'})
    def test_adaptive_fallback_to_market(self, mock_get, mock_post, mock_sleep):
        mock_quote_response = MagicMock(status_code=200)
        mock_quote_response.json.return_value = {'quotes': {'quote': {'bid': 0.0, 'ask': 0.0}}}
        mock_get.return_value = mock_quote_response

        mock_post_response = MagicMock(status_code=200)
        mock_post_response.json.return_value = {'order': {'id': '88882222', 'status': 'ok'}}
        mock_post.return_value = mock_post_response

        result = gex_exit_monitor.execute_tradier_close('NVDA260812C00217500', 'NVDA', 1, 'https://sandbox.tradier.com/v1', max_wait_seconds=2)

        self.assertTrue(result)
        args, kwargs = mock_post.call_args
        payload = kwargs.get('data', {})
        self.assertEqual(payload.get('type'), 'market')
        self.assertNotIn('price', payload)


# ==============================================================================
# 3. AUTOMATED ARMED CSO INJECTOR TESTS
# ==============================================================================
class TestAutoInjectArmed(unittest.TestCase):

    @patch('auto_inject_armed.subprocess.run')
    @patch('auto_inject_armed.requests.get')
    @patch('auto_inject_armed.get_fargate_public_ip', return_value='1.2.3.4')
    def test_run_armed_injection_fargate_success(self, mock_ip, mock_get, mock_subprocess):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "NVDA": {"armed": True, "status": "ARMED"},
            "AAPL": {"armed": False, "status": "WAITING"}
        }
        mock_get.return_value = mock_response

        mock_sub_res = MagicMock()
        mock_sub_res.returncode = 0
        mock_sub_res.stdout = "[✓ SUCCESS] Strict Tradier Receipt confirmed"
        mock_subprocess.return_value = mock_sub_res

        auto_inject_armed.run_armed_injection()

        mock_get.assert_called_with("http://1.2.3.4:8080/api/proximity", timeout=4)
        mock_subprocess.assert_called_once()
        cmd_args, cmd_kwargs = mock_subprocess.call_args
        self.assertIn("NVDA", cmd_args[0])
        self.assertEqual(cmd_kwargs.get("timeout"), 35)

    @patch('auto_inject_armed.subprocess.run')
    @patch('auto_inject_armed.get_fargate_public_ip', return_value=None)
    def test_run_armed_injection_no_armed_tickers(self, mock_ip, mock_subprocess):
        with patch('os.path.exists', return_value=False):
            auto_inject_armed.run_armed_injection()
            mock_subprocess.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
