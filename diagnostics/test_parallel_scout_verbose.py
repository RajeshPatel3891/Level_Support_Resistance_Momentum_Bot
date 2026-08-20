import unittest
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

def evaluate_candidate(ticker):
    import smart_cso_injector
    try:
        spot, target, prox_score = smart_cso_injector.get_gex_target_info(ticker)
        return {'ticker': ticker, 'prox': prox_score, 'spot': spot, 'target': target, 'err': None}
    except Exception as e:
        return {'ticker': ticker, 'prox': 0.0, 'spot': 0.0, 'target': 0.0, 'err': str(e)}

class TestParallelScoutEngineVerbose(unittest.TestCase):

    def setUp(self):
        self.mock_injector = MagicMock()
        self.patcher = patch.dict('sys.modules', {'smart_cso_injector': self.mock_injector})
        self.patcher.start()
        self.target_pool = ['PLTR', 'HOOD', 'SOFI', 'F', 'AAL', 'CCL', 'UBER', 'MARA']

    def tearDown(self):
        self.patcher.stop()

    def test_parallel_ranking_order(self):
        import smart_cso_injector
        print("\n" + "=" * 70)
        print(" 🧪 TEST 1: PARALLEL EVALUATION & LEADERBOARD RANKING")
        print("=" * 70)
        
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

        print(f"[*] Scanning {len(self.target_pool)} tickers concurrently via ThreadPoolExecutor...")
        candidates = []
        with ThreadPoolExecutor(max_workers=len(self.target_pool)) as executor:
            futures = {executor.submit(evaluate_candidate, t): t for t in self.target_pool}
            for future in as_completed(futures):
                res = future.result()
                if not res['err']:
                    candidates.append(res)

        candidates.sort(key=lambda x: x['prox'], reverse=True)

        print("\n📊 DYNAMIC RANKING LEADERBOARD (HIGHEST CONVICTION FIRST):")
        print("-" * 70)
        print(f"{'Rank':<6} | {'Ticker':<8} | {'Spot Price':<12} | {'Target Price':<12} | {'Proximity Score':<15}")
        print("-" * 70)
        for idx, item in enumerate(candidates, 1):
            print(f"#{idx:<5} | {item['ticker']:<8} | ${item['spot']:<11.2f} | ${item['target']:<11.2f} | {item['prox']:>6.1f}%")
        print("-" * 70)

        self.assertEqual(candidates[0]['ticker'], 'SOFI')
        self.assertEqual(candidates[1]['ticker'], 'MARA')
        self.assertEqual(candidates[2]['ticker'], 'PLTR')
        self.assertEqual(candidates[-1]['ticker'], 'CCL')

    def test_threshold_gate_and_single_fill_halt(self):
        import smart_cso_injector
        print("\n" + "=" * 70)
        print(" 🧪 TEST 2: THRESHOLD GATING (>=75%) & SINGLE-FILL HALT")
        print("=" * 70)
        
        mock_data = {
            'PLTR': (30.0, 32.0, 70.0),
            'SOFI': (8.0, 9.0, 85.0),
            'MARA': (18.0, 20.0, 95.0)
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
            ticker = item['ticker']
            prox = item['prox']
            print(f"\n -> Evaluating Rank #{candidates.index(item)+1}: {ticker} ({prox:.1f}% Proximity)")
            
            if prox < 75.0:
                print(f"    ⚠️ [SKIPPED] Proximity {prox:.1f}% below 75.0% threshold requirement.")
                continue

            print(f"    🚀 [TRIGGERED] Conviction threshold met! Executing broker order for {ticker}...")
            smart_cso_injector.smart_cso_scout_and_execute(force_ticker=ticker, contract_qty=1)
            
            if smart_cso_injector.check_active_position_exists(ticker):
                print(f"    🎉 [SINGLE-FILL CONFIRMED] Active position verified for {ticker}! Halting scout engine.")
                executed_ticker = ticker
                break

        self.assertEqual(executed_ticker, 'MARA')

if __name__ == '__main__':
    unittest.main()
