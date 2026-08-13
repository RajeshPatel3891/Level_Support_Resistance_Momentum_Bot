import unittest
from unittest.mock import patch, MagicMock
import os
import sys

import auto_inject_armed

class TestAutoInjectArmed(unittest.TestCase):

    @patch('auto_inject_armed.subprocess.run')
    @patch('auto_inject_armed.requests.get')
    @patch('auto_inject_armed.get_fargate_public_ip', return_value='1.2.3.4')
    def test_run_armed_injection_fargate_success(self, mock_ip, mock_get, mock_subprocess):
        # 1. Mock successful Fargate API response returning NVDA as ARMED
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "NVDA": {"armed": True, "status": "ARMED"},
            "AAPL": {"armed": False, "status": "WAITING"}
        }
        mock_get.return_value = mock_response

        # 2. Mock subprocess execution for smart_cso_injector.py
        mock_sub_res = MagicMock()
        mock_sub_res.returncode = 0
        mock_sub_res.stdout = "[✓ SUCCESS] Strict Tradier Receipt confirmed"
        mock_subprocess.return_value = mock_sub_res

        # 3. Execute daemon
        auto_inject_armed.run_armed_injection()

        # 4. Assert Fargate proximity endpoint was queried
        mock_get.assert_called_with("http://1.2.3.4:8080/api/proximity", timeout=4)

        # 5. Assert subprocess was triggered ONLY for NVDA with expanded 35s timeout
        mock_subprocess.assert_called_once()
        cmd_args, cmd_kwargs = mock_subprocess.call_args
        self.assertIn("NVDA", cmd_args[0])
        self.assertEqual(cmd_kwargs.get("timeout"), 35)

    @patch('auto_inject_armed.subprocess.run')
    @patch('auto_inject_armed.get_fargate_public_ip', return_value=None)
    def test_run_armed_injection_no_armed_tickers(self, mock_ip, mock_subprocess):
        # Simulate local fallback with no ARMED tickers
        mock_levels = {
            "AAPL": {"spot": 300.0, "algo_macro": {"target": ["$300.00"]}} # gap = 0% -> ARMED
        }
        
        with patch('os.path.exists', return_value=False):
            auto_inject_armed.run_armed_injection()
            # Subprocess should never fire if no tickers are ARMED
            mock_subprocess.assert_not_called()

if __name__ == '__main__':
    unittest.main()
