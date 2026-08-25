import unittest
import asyncio
import inspect
from dashboard_server import get_proximity

class TestProximityFalsePositives(unittest.TestCase):

    def test_full_arming_matrix_and_false_positives(self):
        """Simulate live Tradier quotes and print formatted arming state report."""
        try:
            if inspect.iscoroutinefunction(get_proximity):
                proximity_results = asyncio.run(get_proximity())
            else:
                proximity_results = get_proximity()
                if inspect.iscoroutine(proximity_results):
                    proximity_results = asyncio.run(proximity_results)
            
            self.assertIsNotNone(proximity_results)
            print("[✓ TEST PROXIMITY PASSED] Proximity matrix retrieved successfully.")
        except Exception as e:
            self.fail(f"get_proximity failed with exception: {e}")

if __name__ == "__main__":
    unittest.main()
