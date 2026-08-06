import os
import sys
import sqlite3
import unittest
from unittest.mock import patch, MagicMock

# Store true sqlite3.connect reference prior to patching to prevent infinite recursion
REAL_SQLITE_CONNECT = sqlite3.connect

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from src.LiveBot import execute_order

class TestLiveBotActiveGuard(unittest.TestCase):
    def setUp(self):
        """Set up a fresh temporary SQLite database for testing."""
        self.db_path = "test_harm_telemetry.db"
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            
        conn = REAL_SQLITE_CONNECT(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                timestamp TEXT,
                strategy TEXT,
                direction TEXT,
                spot_price REAL,
                entry_price REAL,
                shares REAL,
                stop_loss REAL,
                take_profit REAL,
                net_pnl REAL,
                exit_status TEXT,
                is_live INTEGER,
                occ_symbol TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS account_ledger (
                date TEXT PRIMARY KEY,
                starting_settled_cash REAL,
                available_settled_cash REAL,
                unsettled_cash REAL
            )
        ''')
        conn.commit()
        conn.close()

    def tearDown(self):
        """Clean up test database file after test run."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    @patch('src.LiveBot.sqlite3.connect')
    def test_execute_order_blocked_if_active_trade_exists(self, mock_sqlite_connect):
        """Verify execute_order returns False when an ACTIVE trade exists in the DB."""
        mock_sqlite_connect.side_effect = lambda *args, **kwargs: REAL_SQLITE_CONNECT(self.db_path)

        # Seed an ACTIVE trade for PLTR
        conn = REAL_SQLITE_CONNECT(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trades (ticker, timestamp, exit_status) 
            VALUES ('PLTR', '2026-08-06 12:00:00', 'ACTIVE')
        """)
        conn.commit()
        conn.close()

        # Execute order for PLTR (should be rejected by DB guard)
        result = execute_order('PLTR', 'PLTR', 1.0, 'CALL', limit_price=155.0)

        self.assertFalse(result, "execute_order should return False when ticker is already ACTIVE")

    @patch('src.LiveBot.fetch_occ_option_symbol')
    @patch('src.LiveBot.get_live_quote')
    @patch('src.LiveBot.get_available_settled_cash')
    @patch('src.LiveBot.sqlite3.connect')
    def test_execute_order_passes_guard_if_no_active_trade(
        self, mock_sqlite_connect, mock_cash, mock_quote, mock_occ
    ):
        """Verify execute_order bypasses rejection guard when no ACTIVE trade exists."""
        mock_sqlite_connect.side_effect = lambda *args, **kwargs: REAL_SQLITE_CONNECT(self.db_path)
        mock_cash.return_value = 5000.0
        mock_quote.return_value = {'ask': 1.50, 'bid': 1.45, 'last': 1.50}
        mock_occ.return_value = 'NVDA260806C00200000'

        # Seed a CLOSED trade for NVDA (not ACTIVE)
        conn = REAL_SQLITE_CONNECT(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trades (ticker, timestamp, exit_status) 
            VALUES ('NVDA', '2026-08-06 10:00:00', 'FORCE_CLOSE')
        """)
        conn.commit()
        conn.close()

        # Mock external Tradier order HTTP call to succeed
        with patch('src.LiveBot.requests.post') as mock_post, \
             patch('src.LiveBot.get_order_status', return_value='filled'):
            
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'order': {'id': 12345}}

            result = execute_order('NVDA', 'NVDA', 1.0, 'CALL', limit_price=200.0)

            self.assertTrue(result, "execute_order should proceed and return True when no ACTIVE trade exists")

if __name__ == '__main__':
    unittest.main()
