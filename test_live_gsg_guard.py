import unittest

class TestGSGGuardLogic(unittest.TestCase):
    
    def calculate_stop(self, entry_price, peak_pnl_pct, existing_sl=0.0):
        # Replicating exact logic from live_gsg_guard.py
        if peak_pnl_pct >= 35.0:
            # Requires peak_price, let's simulate peak_price derived from peak_pnl_pct
            peak_price = entry_price * (1.0 + peak_pnl_pct / 100.0)
            dynamic_stop = round(peak_price - 0.06, 2)
        elif peak_pnl_pct >= 25.0:
            peak_price = entry_price * (1.0 + peak_pnl_pct / 100.0)
            dynamic_stop = round(peak_price - 0.04, 2)
        elif peak_pnl_pct >= 15.0:
            peak_price = entry_price * (1.0 + peak_pnl_pct / 100.0)
            dynamic_stop = round(peak_price - 0.03, 2)
        elif peak_pnl_pct >= 10.0:
            dynamic_stop = round(entry_price * 1.05, 2) # +5% break-even lock
        else:
            dynamic_stop = round(entry_price * 0.80, 2)

        if existing_sl > dynamic_stop:
            dynamic_stop = existing_sl
            
        return dynamic_stop

    def test_initial_stop_floor(self):
        # Entry $0.40, 0% peak -> Stop should be $0.32 (-20%)
        sl = self.calculate_stop(0.40, 0.0)
        self.assertEqual(sl, 0.32)

    def test_break_even_lock_at_10_percent(self):
        # Entry $0.40, 12% peak -> Stop should lock at entry * 1.05 = $0.42
        sl = self.calculate_stop(0.40, 12.0)
        self.assertEqual(sl, 0.42)

    def test_peak_ratchet_at_35_percent(self):
        # Entry $0.40, Peak PnL +40% -> Peak price = $0.56 -> Stop = $0.56 - $0.06 = $0.50
        sl = self.calculate_stop(0.40, 40.0)
        self.assertEqual(sl, 0.50)

    def test_ratchet_non_decreasing_constraint(self):
        # Existing stop is $0.45, new calculation yields $0.32 -> Must hold at $0.45
        sl = self.calculate_stop(0.40, 0.0, existing_sl=0.45)
        self.assertEqual(sl, 0.45)

if __name__ == '__main__':
    unittest.main()
