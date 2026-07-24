import unittest
import sys
import os

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from src.RiskEngine import (
    calculate_gex_hit_probability,
    calculate_risk_return_dollars,
    evaluate_cso_informed_exit
)

class TestRiskEngineMatrix(unittest.TestCase):

    def test_risk_reward_ratio(self):
        tp_return, sl_risk = calculate_risk_return_dollars(spot=14.37, target=14.59, stop_loss=14.23, shares=1.0, delta=0.50)
        rr = round(abs(tp_return) / abs(sl_risk), 2)
        self.assertEqual(rr, 1.57)

    def test_cso_take_profit_now_recommendation(self):
        # Spot $14.37, Target $14.59, Stop $14.23, Prob 35.4%, Floating Open PnL +$1.25
        # TP Reward = +$11.00, SL Risk = -$7.00
        # EV = (0.354 * 11) - (0.646 * 7) = 3.894 - 4.522 = -$0.63 (Negative EV while in profit -> TAKE_PROFIT_NOW)
        eval_result = evaluate_cso_informed_exit(
            spot=14.37, target=14.59, stop_loss=14.23,
            prob_win=35.4, floating_pnl=1.25, shares=1.0, delta=0.50
        )
        self.assertEqual(eval_result["recommendation"], "TAKE_PROFIT_NOW")
        self.assertLess(eval_result["ev_dollars"], 0.0)

if __name__ == '__main__':
    unittest.main()
