import unittest
import json
import os
import tempfile
import harmonized_bot_streamer
from dashboard_server import get_proximity

class TestProximityFalsePositives(unittest.TestCase):

    def setUp(self):
        """Build a realistic multi-ticker level manifest."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.levels_path = os.path.join(self.temp_dir.name, 'trading_levels.json')
        
        self.mock_manifest = {
            "F": {
                "spot": 13.98,
                "vwap": 13.98,
                "algo_macro": {"target": ["$14.06"]},
                "support_zone": [13.00, 13.50],
                "resistance_zone": [14.50, 15.00]
            },
            "SOFI": {
                "spot": 18.38,
                "vwap": 18.38,
                "algo_macro": {"target": ["$18.50"]},
                "support_zone": [17.00, 17.50],
                "resistance_zone": [19.00, 19.50]
            },
            "AAL": {
                "spot": 15.94,
                "vwap": 15.94,
                "algo_macro": {"target": ["$16.36"]},
                "support_zone": [14.00, 14.50],
                "resistance_zone": [17.00, 17.50]
            },
            "RIVN": {
                "spot": 16.00,
                "vwap": 16.00,
                "algo_macro": {"target": ["$16.11"]},
                "support_zone": [15.00, 15.50],
                "resistance_zone": [17.00, 17.50]
            }
        }
        
        with open(self.levels_path, 'w') as f:
            json.dump(self.mock_manifest, f, indent=4)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_full_arming_matrix_and_false_positives(self):
        """Simulate live Tradier quotes and print formatted arming state report."""
        live_quotes = {
            "F": 14.02,
            "RIVN": 16.07,
            "SOFI": 18.26,
            "AAL": 15.49
        }
        
        orig_streamer_file = harmonized_bot_streamer.LEVELS_FILE
        harmonized_bot_streamer.LEVELS_FILE = self.levels_path
        
        try:
            streamer = harmonized_bot_streamer.HarmonizedBotStreamer.__new__(harmonized_bot_streamer.HarmonizedBotStreamer)
            streamer.update_levels_file_spot_prices(live_quotes)
            
            orig_cwd = os.getcwd()
            os.chdir(self.temp_dir.name)
            
            try:
                import asyncio
                proximity_results = asyncio.run(get_proximity())
                
                # Print explicit stdout breakdown matrix
                print("\n==========================================================")
                print("🦅 HARM.AI // PROXIMITY MATRIX EVALUATION REPORT")
                print("==========================================================")
                print(f"{'TICKER':<8} | {'SPOT':<8} | {'TARGET':<8} | {'GAP %':<8} | {'ARMING STATUS'}")
                print("-" * 58)
                
                for ticker, data in proximity_results.items():
                    status_str = f"🟢 {data['status']}" if data["armed"] else f"⚪ {data['status']}"
                    print(f"{ticker:<8} | ${data['spot']:<7.2f} | {data['target']:<8} | {data['gap_pct']:<8} | {status_str}")
                print("==========================================================\n")
                
                # Assert ARMED states (True Positives)
                self.assertTrue(proximity_results["F"]["armed"], "F should be ARMED")
                self.assertTrue(proximity_results["RIVN"]["armed"], "RIVN should be ARMED")
                
                # Assert WAITING states (Catch False Positives)
                self.assertFalse(proximity_results["SOFI"]["armed"], "SOFI must be WAITING")
                self.assertFalse(proximity_results["AAL"]["armed"], "AAL must be WAITING")
                
            finally:
                os.chdir(orig_cwd)
        finally:
            harmonized_bot_streamer.LEVELS_FILE = orig_streamer_file

if __name__ == "__main__":
    unittest.main()
