import unittest
import sqlite3
import os
from datetime import datetime, timedelta
from src.smart_cso_injector import validate_reentry_eligibility

TEST_DB_PATH = "test_harm_telemetry.db"

class TestSmartCSOInjector(unittest.TestCase):

    def setUp(self):
        """Set up clean SQLite test DB schema."""
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        conn = sqlite3.connect(TEST_DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE trades (
                ticker TEXT,
                timestamp TEXT,
                status TEXT
            )
        """)
        conn.commit()
        conn.close()

    def tearDown(self):
        """Clean up test database artifact."""
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

    def test_reentry_cooldown_and_daily_cap(self):
        """Asserts 15-minute cooldown blocks premature re-entry and 2-trade cap stops 3rd attempt."""
        conn = sqlite3.connect(TEST_DB_PATH)
        c = conn.cursor()

        self.assertTrue(validate_reentry_eligibility("SOFI", TEST_DB_PATH))

        # 1. Test 15-min cooldown
        now = datetime.now()
        time_5m_ago = (now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO trades VALUES (?, ?, 'CLOSED')", ("SOFI", time_5m_ago))
        conn.commit()

        self.assertFalse(validate_reentry_eligibility("SOFI", TEST_DB_PATH))

        # 2. Test 2-trade daily cap
        c.execute("DELETE FROM trades")
        time_25m_ago = (now - timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S")
        time_20m_ago = (now - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO trades VALUES (?, ?, 'CLOSED')", ("SOFI", time_25m_ago))
        c.execute("INSERT INTO trades VALUES (?, ?, 'CLOSED')", ("SOFI", time_20m_ago))
        conn.commit()

        self.assertFalse(validate_reentry_eligibility("SOFI", TEST_DB_PATH))
        conn.close()

        print("[✓ TEST RE-ENTRY GUARDRAILS] 15m Cooldown and 2-Trade Daily Cap enforced successfully.")

if __name__ == "__main__":
    unittest.main()
