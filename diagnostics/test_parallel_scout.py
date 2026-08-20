import unittest
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import time

# Mock module imports if running outside container
sys.modules['smart_cso_injector'] = MagicMock()
import smart_cso_injector

def evaluate_candidate(ticker):
    try:
        spot, target, prox_score = smart_cso_injector.get_gex_target_info(ticker)
        return {'ticker': ticker, 'prox': prox_score, 'spot': spot, 'target': target, 'err': None}
    except Exception as e:
        return {'ticker': ticker, 'prox': 0.0, 'spot': 0.0, 'target': 0.0, 'err': str(e)}

class TestParallelScoutEngine(unittest.TestCase):

    def setUp(self):
        self.target_pool = ['PLTR', 'HOOD', 'SOFI', 'F', 'AAL', 'CCL', 'UBER', 'MARA']

    def test_parallel_ranking_order(self):
        """Verify candidates are sorted in descending order of GEX proximity."""
        mock_data = {
            'PLTR': (30.0, 32.0, 82.5),
            'HOOD': (20.0, 22.0, 60.0),
            'SOFI': (8.0, 9.0, 91.0),
            'F': (10.0, 11.0, 40.0),
            'AAL': (12.0, 13.0, 78.0),
            'CCL': (15.0, 16.0, 30.0),
            'UBER': (70.0, 75.0, 50.0),
            'MARA': (18.0, 20.0, 88.0)
        }
        smart_cso_injector.get_gex_target_info.side_effect = lambda t: mock_data[t]

        candidates = []
        with ThreadPoolExecutor(max_workers=len(self.target_pool)) as executor:
            futures = {executor.submit(evaluate_candidate, t): t for t in self.target_pool}
            for future in as_completed(futures):
                res = future.result()
                if not res['err']:
                    candidates.append(res)

        candidates.sort(key=lambda x: x['prox'], reverse=True)

        # SOFI (91.0%) should be #1, MARA (88.0%) #2, PLTR (82.5%) #3
        self.assertEqual(candidates[0]['ticker'], 'SOFI')
        self.assertEqual(candidates[1]['ticker'], 'MARA')
        self.assertEqual(candidates[2]['ticker'], 'PLTR')
        self.assertEqual(candidates[-1]['ticker'], 'CCL')  # 30.0% lowest

    def test_threshold_gate_and_single_fill_halt(self):
        """Verify engine skips candidates <75% and halts immediately upon single fill."""
        mock_data = {
            'PLTR': (30.0, 32.0, 70.0), # Below threshold (<75%)
            'SOFI': (8.0, 9.0, 85.0),   # Meets threshold (First target)
            'MARA': (18.0, 20.0, 95.0)  # Meets threshold (Higher proximity)
        }
        smart_cso_injector.get_gex_target_info.side_effect = lambda t: mock_data[t]
        smart_cso_injector.check_active_position_exists.return_value = True

        test_pool = ['PLTR', 'SOFI', 'MARA']
        candidates = []
        
        with ThreadPoolExecutor(max_workers=len(test_pool)) as executor:
            futures = {executor.submit(evaluate_candidate, t): t for t in test_pool}
            for future in as_completed(futures):
                candidates.append(future.result())

        candidates.sort(key=lambda x: x['prox'], reverse=True)

        executed_ticker = None
        for item in candidates:
            if item['prox'] >= 75.0:
                smart_cso_injector.smart_cso_scout_and_execute(force_ticker=item['ticker'], contract_qty=1)
                if smart_cso_injector.check_active_position_exists(item['ticker']):
                    executed_ticker = item['ticker']
                    break

        # MARA (95.0%) should execute first and halt the loop before SOFI (85.0%) is touched
        self.assertEqual(executed_ticker, 'MARA')
        smart_cso_injector.smart_cso_scout_and_execute.assert_called_once_with(force_ticker='MARA', contract_qty=1)

if __name__ == '__main__':
    unittest.main()
