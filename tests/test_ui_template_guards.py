import unittest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient

class TestDualEnvironmentGuards(unittest.TestCase):
    def test_sandbox_vs_prod_balance_isolation(self):
        """[TEST] Asserts SANDBOX renders 113k baseline while PROD renders dynamic Tradier context."""
        
        # 1. Test Sandbox Mode
        with patch.dict(os.environ, {"ENVIRONMENT": "sandbox"}):
            import dashboard_server
            client_sb = TestClient(dashboard_server.app)
            res_sb = client_sb.get("/")
            self.assertIn("113,210.62", res_sb.text, "❌ REGRESSION: Sandbox mode failed to render $113,210.62 baseline!")

        # 2. Test Production Mode
        mock_portfolio = ([], [], 0.0, 0.0, "2026-08-24", 5565.24, 5565.24, 0.0, 0.0)
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            with patch("dashboard_server.fetch_portfolio_state", return_value=mock_portfolio):
                import dashboard_server
                client_prod = TestClient(dashboard_server.app)
                res_prod = client_prod.get("/")
                self.assertIn("5,565.24", res_prod.text, "❌ REGRESSION: Production mode failed to render dynamic account balance!")
                self.assertNotIn("113,210.62", res_prod.text, "❌ REGRESSION: Production mode still rendering hardcoded 113k baseline!")

if __name__ == "__main__":
    unittest.main()
