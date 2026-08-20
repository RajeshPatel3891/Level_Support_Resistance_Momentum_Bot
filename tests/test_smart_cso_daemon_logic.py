#!/usr/bin/env python3
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.extend([".", "src", "/app", "/app/src"])

import smart_cso_daemon

class TestSmartCSODaemonLogic(unittest.TestCase):

    @patch("smart_cso_injector.smart_cso_scout_and_execute")
    def test_single_fill_circuit_breaker(self, mock_scout):
        """Asserts that the daemon terminates the scan loop immediately on the 1st fill."""
        # Setup: SOFI returns None, F returns filled dictionary
        mock_scout.side_effect = [
            None,  # SOFI -> Unfilled
            {"status": "FILLED", "ticker": "F", "order_id": "12345"}  # F -> Filled
        ]

        # Execute
        smart_cso_daemon.run_daemon_loop()

        # Assertions
        self.assertEqual(mock_scout.call_count, 2, "Daemon should stop immediately after the 2nd ticker fills!")
        mock_scout.assert_any_call("SOFI")
        mock_scout.assert_any_call("F")
        print("\n[✓ UNIT TEST PASSED] Circuit breaker verified: Daemon stopped immediately on 1st fill!")

    @patch("smart_cso_injector.smart_cso_scout_and_execute")
    @patch("time.sleep", return_value=None)
    def test_continues_scanning_when_unfilled(self, mock_sleep, mock_scout):
        """Asserts daemon keeps scanning all tickers if zero fills occur in first pass."""
        mock_scout.return_value = None  # No fills

        # Force loop break after 7 calls (1 full pass of armed_tickers)
        def side_effect(ticker):
            if mock_scout.call_count >= 7:
                raise KeyboardInterrupt("Simulated Loop Break")
            return None

        mock_scout.side_effect = side_effect

        with self.assertRaises(KeyboardInterrupt):
            smart_cso_daemon.run_daemon_loop()

        self.assertEqual(mock_scout.call_count, 7, "Daemon should scan all 7 tickers if no fill occurs!")
        print("[✓ UNIT TEST PASSED] Full sweep verified: Scanned all 7 targets without premature exit!")

if __name__ == "__main__":
    unittest.main()
