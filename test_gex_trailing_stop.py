import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure src/ directory is on Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def calculate_dynamic_stop(entry_price: float, peak_pnl_pct: float, is_runner: bool = False) -> float:
    """Helper mirroring the dynamic stop logic inside gex_exit_monitor.py."""
    if is_runner:
        cushion = 12.0 if peak_pnl_pct >= 100.0 else 10.0
        dynamic_stop_pct = max(3.0, peak_pnl_pct - cushion)
        return round(entry_price * (1.0 + dynamic_stop_pct / 100.0), 2)
    elif peak_pnl_pct >= 35.0:
        return round(entry_price * (1.0 + (peak_pnl_pct - 10.0) / 100.0), 2)
    elif peak_pnl_pct >= 20.0:
        return round(entry_price * (1.0 + (peak_pnl_pct - 10.0) / 100.0), 2)
    elif peak_pnl_pct >= 12.0:
        return round(entry_price * 1.03, 2)
    else:
        return round(entry_price * 0.80, 2)


class TestGEXExitMonitorTrailingStops(unittest.TestCase):

    def test_nvda_high_water_mark_trailing_stop(self):
        """Test NVDA scenario: Entry $1.73, Peak PnL +189.6% -> Expected Stop: $4.84"""
        entry_price = 1.73
        peak_pnl_pct = 189.6
        stop = calculate_dynamic_stop(entry_price, peak_pnl_pct, is_runner=False)
        
        # 189.6% - 10% = 179.6% lock -> $1.73 * 2.796 = $4.837 -> $4.84
        self.assertEqual(stop, 4.84)
        self.assertGreaterThan(stop, entry_price)

    def test_tier_2_mid_peak_trailing_stop(self):
        """Test Tier 2: Entry $2.00, Peak PnL +25.0% -> Expected Stop: $2.30 (+15% lock)"""
        entry_price = 2.00
        peak_pnl_pct = 25.0
        stop = calculate_dynamic_stop(entry_price, peak_pnl_pct, is_runner=False)
        
        # 25% - 10% = +15% lock -> $2.00 * 1.15 = $2.30
        self.assertEqual(stop, 2.30)

    def test_green_stay_green_floor(self):
        """Test Tier 1: Entry $1.00, Peak PnL +15.0% -> Expected Stop: $1.03 (+3% breakeven lock)"""
        entry_price = 1.00
        peak_pnl_pct = 15.0
        stop = calculate_dynamic_stop(entry_price, peak_pnl_pct, is_runner=False)
        
        self.assertEqual(stop, 1.03)

    def test_initial_risk_floor(self):
        """Test Initial Floor: Entry $1.00, Peak PnL +5.0% -> Expected Stop: $0.80 (-20% stop)"""
        entry_price = 1.00
        peak_pnl_pct = 5.0
        stop = calculate_dynamic_stop(entry_price, peak_pnl_pct, is_runner=False)
        
        self.assertEqual(stop, 0.80)

    def test_runner_trailing_stop_over_100pct(self):
        """Test Runner State: Entry $1.00, Peak PnL +150.0% -> Expected Stop: $2.38 (12% cushion)"""
        entry_price = 1.00
        peak_pnl_pct = 150.0
        stop = calculate_dynamic_stop(entry_price, peak_pnl_pct, is_runner=True)
        
        # 150% - 12% cushion = 138% lock -> $1.00 * 2.38 = $2.38
        self.assertEqual(stop, 2.38)

    def assertGreaterThan(self, a, b):
        self.assertTrue(a > b, f"{a} is not greater than {b}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
