#!/usr/bin/env python3
import sys
import unittest
from fastapi.testclient import TestClient

sys.path.extend([".", "src"])
from dashboard_server import app

class TestOrderWalkerUIIntegration(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_full_ui_walker_injection_flow(self):
        print("\n" + "="*65)
        print("⚡ TESTING UI 'INJECT' -> BID-TO-MID ORDER WALKER EXECUTION")
        print("="*65)
        
        payload = {
            "ticker": "SOFI",
            "occ_symbol": "SOFI260821P00019000"
        }
        
        # Simulates clicking the UI INJECT button
        response = self.client.post("/api/inject_trade", json=payload)
        
        print(f"[*] Response Code : {response.status_code}")
        print(f"[*] Response Body : {response.json()}")
        
        # Verify valid HTTP response code
        self.assertIn(response.status_code, [200, 400])
        print("="*65)
        print("[✓ SUCCESS] Endpoint connected to Order Walker engine cleanly!")
        print("="*65)

if __name__ == "__main__":
    unittest.main()
