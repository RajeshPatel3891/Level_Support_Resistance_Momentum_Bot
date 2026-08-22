#!/usr/bin/env python3
"""
HARM.AI // LOCAL JINJA DIV & FASTAPI INJECT ENDPOINT UNIT TEST
===============================================================================
Tests:
  1. Jinja2 template rendering of the Proximity Matrix / Inject DIV structure.
  2. Mock execution of /api/inject_trade using the Dynamic Order Walker.
"""

import os
import sys
import unittest
from fastapi.testclient import TestClient

# Ensure root path is in sys.path
sys.path.extend([".", "src"])

# Import app instance from dashboard_server
from dashboard_server import app

class TestDashboardUIAndInject(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_01_index_html_div_rendering(self):
        """Verify the Jinja template correctly renders proximity container and script blocks."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        
        html_content = response.text
        
        # Check that essential HTML divs and JS handlers are present
        self.assertIn('id="proximity-container"', html_content)
        self.assertIn('function triggerUiInjectStream(ticker)', html_content)
        self.assertIn('LEVEL PROXIMITY MATRIX', html_content)
        print("\n[✓ TEST 1 PASSED] Jinja HTML Template & Matrix DIV rendered successfully.")

    def test_02_inject_trade_endpoint_validation(self):
        """Verify /api/inject_trade route structure handles missing parameters cleanly."""
        # Test bad request payload
        response = self.client.post("/api/inject_trade", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Missing ticker or occ_symbol", response.json().get("reason", ""))
        print("[✓ TEST 2 PASSED] /api/inject_trade payload validation verified.")

if __name__ == "__main__":
    unittest.main()
