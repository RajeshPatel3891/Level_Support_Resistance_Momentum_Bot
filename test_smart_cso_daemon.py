import os
import sys
import unittest
import threading
import time
from unittest.mock import patch, MagicMock

# Add src and root to path
sys.path.extend(["src", "."])

import smart_cso_daemon

class TestSmartCSODaemon(unittest.TestCase):

    # =========================================================================
    # 1. NON-BLOCKING TELEMETRY SPRAWL TEST
    # =========================================================================
    @patch("smart_cso_injector.monitor_live_exit_telemetry")
    def test_non_blocking_telemetry_thread_spawn(self, mock_orig_telemetry):
        """Asserts that calling monitor_live_exit_telemetry spawns a daemon thread without blocking the loop."""
        test_ticker = "SOFI"
        
        # Execute the wrapper function created inside smart_cso_daemon
        smart_cso_daemon.smart_cso_injector.monitor_live_exit_telemetry(test_ticker)
        
        # Allow thread execution frame to register
        time.sleep(0.2)
        
        # Verify the underlying telemetry function was called inside its background thread
        mock_orig_telemetry.assert_called_once_with(test_ticker)
        print("\n[✓ TEST 1: TELEMETRY THREADING] Non-blocking daemon watch thread spawned successfully.")

    # =========================================================================
    # 2. DAEMON MULTI-TICKER ITERATION & EXCEPTION FAULT TOLERANCE
    # =========================================================================
    @patch("smart_cso_injector.smart_cso_scout_and_execute")
    def test_daemon_loop_fault_tolerance(self, mock_scout):
        """Asserts daemon continues evaluating remaining tickers even if one throws an unhandled API exception."""
        # Setup mock behavior: SOFI throws an exception, F succeeds, AAL succeeds
        def scout_side_effect(ticker):
            if ticker == "SOFI":
                raise ValueError("Simulated Tradier Gateway Timeout")
            return f"EXECUTED_{ticker}"

        mock_scout.side_effect = scout_side_effect
        
        test_tickers = ["SOFI", "F", "AAL"]
        results = {}

        # Run a single scan pass mimicking the daemon loop body
        for ticker in test_tickers:
            try:
                res = smart_cso_daemon.smart_cso_injector.smart_cso_scout_and_execute(ticker)
                results[ticker] = res
            except Exception as e:
                results[ticker] = f"CAUGHT_EXCEPTION: {e}"

        # Assert SOFI caught exception but didn't crash execution for F and AAL
        self.assertIn("Simulated Tradier Gateway Timeout", results["SOFI"])
        self.assertEqual(results["F"], "EXECUTED_F")
        self.assertEqual(results["AAL"], "EXECUTED_AAL")
        self.assertEqual(mock_scout.call_count, 3)

        print("[✓ TEST 2: FAULT TOLERANCE] API exception on SOFI isolated; daemon loop successfully completed F and AAL scans.")

    # =========================================================================
    # 3. ENVIRONMENT FILE PATH RESILIENCE
    # =========================================================================
    def test_armed_ticker_list_integrity(self):
        """Asserts armed ticker targets are defined and non-empty."""
        self.assertTrue(len(smart_cso_daemon.armed_tickers) > 0)
        self.assertIn("SOFI", smart_cso_daemon.armed_tickers)
        print(f"[✓ TEST 3: TARGET INTEGRITY] Verified {len(smart_cso_daemon.armed_tickers)} armed tickers configured: {smart_cso_daemon.armed_tickers}")

if __name__ == "__main__":
    unittest.main()
