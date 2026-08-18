import os
import sys
import unittest
import sqlite3
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add src and root to path
sys.path.extend(["src", "."])

from smart_cso_injector import (
    get_smoothed_option_mark,
    is_valid_signal_exit,
    validate_reentry_eligibility
)

TEST_DB_PATH = "test_harm_telemetry.db"

class TestSmartCSOInjector(unittest.TestCase):

    def setUp(self):
        """Provision a clean temp SQLite DB for re-entry guardrail testing."""
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        conn = sqlite3.connect(TEST_DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE trades (
                ticker TEXT,
                timestamp TEXT,
                exit_status TEXT
            )
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        """Clean up temp test DB."""
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    # =========================================================================
    # 1. QUOTE SMOOTHING (NOISE FILTER) TEST
    # =========================================================================
    @patch("smart_cso_injector.requests.get")
    def test_quote_smoothing_filters_outlier(self, mock_get):
        """Asserts rolling quote smoothing returns median mark, filtering 1-tick spread spikes."""
        mock_res_1 = MagicMock()
        mock_res_1.json.return_value = {"quotes": {"quote": {"bid": 0.34, "ask": 0.36}}}
        
        mock_res_2 = MagicMock()
        mock_res_2.json.return_value = {"quotes": {"quote": {"bid": 0.18, "ask": 0.22}}}
        
        mock_res_3 = MagicMock()
        mock_res_3.json.return_value = {"quotes": {"quote": {"bid": 0.33, "ask": 0.35}}}
        
        mock_get.side_effect = [mock_res_1, mock_res_2, mock_res_3]

        smoothed_mark = get_smoothed_option_mark("SOFI260821C00018000", samples=3)
        
        print(f"\n[✓ TEST 1: QUOTE SMOOTHING] Raw ticks ($0.35, $0.20, $0.34) -> Smoothed Median: ${smoothed_mark:.2f}")
        self.assertEqual(smoothed_mark, 0.34)

    # =========================================================================
    # 2. UNDERLYING STOCK CONFIRMATION TEST
    # =========================================================================
    def test_underlying_stock_confirmation_logic(self):
        """Asserts option drops (-12%) are IGNORED if stock holds support, but EXECUTE if support breaks or -20% hit."""
        ticker = "SOFI"
        support_level = 18.00

        res_a = is_valid_signal_exit(ticker, spot_price=18.20, option_pnl_pct=-12.0, support_level=support_level)
        self.assertFalse(res_a)

        res_b = is_valid_signal_exit(ticker, spot_price=17.90, option_pnl_pct=-12.0, support_level=support_level)
        self.assertTrue(res_b)

        res_c = is_valid_signal_exit(ticker, spot_price=18.50, option_pnl_pct=-21.0, support_level=support_level)
        self.assertTrue(res_c)

        print("[✓ TEST 2: STOCK CONFIRMATION] Spread noise ignored when stock holds support; exits triggered on support breach or -20% stop.")

    # =========================================================================
    # 3. RE-ENTRY GUARDRAILS TEST (COOLDOWN & DAILY CAP)
    # =========================================================================
    def test_reentry_cooldown_and_daily_cap(self):
        """Asserts 15-minute cooldown blocks premature re-entry and 2-trade cap stops 3rd attempt."""
        conn = sqlite3.connect(TEST_DB_PATH)
        c = conn.cursor()

        self.assertTrue(validate_reentry_eligibility("SOFI", TEST_DB_PATH))

        time_5m_ago = (datetime.now() - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO trades VALUES (?, ?, 'CLOSED')", ("SOFI", time_5m_ago))
        conn.commit()

        self.assertFalse(validate_reentry_eligibility("SOFI", TEST_DB_PATH))

        c.execute("DELETE FROM trades")
        time_1h_ago = (datetime.now() - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")
        time_40m_ago = (datetime.now() - timedelta(minutes=40)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO trades VALUES (?, ?, 'CLOSED')", ("SOFI", time_1h_ago))
        c.execute("INSERT INTO trades VALUES (?, ?, 'CLOSED')", ("SOFI", time_40m_ago))
        conn.commit()
        conn.close()

        self.assertFalse(validate_reentry_eligibility("SOFI", TEST_DB_PATH))

        print("[✓ TEST 3: RE-ENTRY GUARDRAILS] 15m Cooldown and 2-Trade Daily Cap enforced successfully.")

if __name__ == "__main__":
    unittest.main()
