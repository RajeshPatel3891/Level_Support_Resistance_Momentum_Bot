import unittest
import sys
import os

sys.path.extend([".", "src", "/app", "/app/src"])

def evaluate_cso_momentum_exit(ticker, spot_price, support_level, option_pnl_pct):
    """
    CSO Early Exit Evaluator:
    1. Hard Stop Ceiling (<= -20%): Immediate exit.
    2. CSO Soft Stop Band (-8% to -19.9%): Evaluates underlying stock vs support level.
       - If spot < support_level -> Real breakdown -> CSO Early Cut (-8% to -15% loss).
       - If spot >= support_level -> Spread noise -> HOLD.
    3. Normal Band (> -8%): HOLD.
    """
    if option_pnl_pct <= -20.0:
        return "HARD_STOP_20PCT", "Hard safety floor breached."
    
    if -20.0 < option_pnl_pct <= -8.0:
        if spot_price < support_level:
            return "CSO_EARLY_MOMENTUM_CUT", f"Stock (${spot_price:.2f}) broke support (${support_level:.2f}). Cutting early at {option_pnl_pct:.1f}%!"
        else:
            return "HOLD", f"Option down {option_pnl_pct:.1f}%, but stock (${spot_price:.2f}) holding support (${support_level:.2f}). Filtering spread noise."
            
    return "HOLD", "Position within normal variance buffer."


class TestCSOMomentumExitLogic(unittest.TestCase):

    def test_scenario_1_spread_noise_hold(self):
        """
        [SCENARIO 1] Option down -12.5% BUT stock holds above support.
        Expectation: CSO holds position and filters noise.
        """
        ticker, spot, support, pnl = "SOFI", 18.05, 17.95, -12.5
        verdict, reason = evaluate_cso_momentum_exit(ticker, spot, support, pnl)
        
        print("\n" + "="*70)
        print("🧪 [SCENARIO 1: OPTION DOWN -12.5% | STOCK HOLDING SUPPORT]")
        print("="*70)
        print(f"  ├─ Ticker / PnL     : {ticker} @ {pnl}%")
        print(f"  ├─ Spot vs Support  : ${spot:.2f} >= ${support:.2f} (Support Intact)")
        print(f"  ├─ CSO Verdict      : {verdict}")
        print(f"  └─ Reasoning        : {reason}")
        print("="*70)
        self.assertEqual(verdict, "HOLD")

    def test_scenario_2_cso_early_cut(self):
        """
        [SCENARIO 2] Option down -12.5% AND stock breaks below support.
        Expectation: CSO cuts trade early at -12.5% instead of taking -20.0% hit.
        """
        ticker, spot, support, pnl = "SOFI", 17.88, 17.95, -12.5
        verdict, reason = evaluate_cso_momentum_exit(ticker, spot, support, pnl)
        
        print("\n" + "="*70)
        print("🧪 [SCENARIO 2: OPTION DOWN -12.5% | STOCK BREAKING SUPPORT]")
        print("="*70)
        print(f"  ├─ Ticker / PnL     : {ticker} @ {pnl}%")
        print(f"  ├─ Spot vs Support  : ${spot:.2f} < ${support:.2f} (Support Broken!)")
        print(f"  ├─ CSO Verdict      : {verdict}")
        print(f"  └─ Saved Capital    : Saved ~7.5% drawdown compared to full -20% stop!")
        print("="*70)
        self.assertEqual(verdict, "CSO_EARLY_MOMENTUM_CUT")

    def test_scenario_3_hard_stop_ceiling(self):
        """
        [SCENARIO 3] Option down -20.5%.
        Expectation: Hard stop triggers regardless of stock price.
        """
        ticker, spot, support, pnl = "SOFI", 18.00, 17.95, -20.5
        verdict, reason = evaluate_cso_momentum_exit(ticker, spot, support, pnl)
        
        print("\n" + "="*70)
        print("🧪 [SCENARIO 3: OPTION DOWN -20.5% | HARD STOP CEILING]")
        print("="*70)
        print(f"  ├─ Ticker / PnL     : {ticker} @ {pnl}%")
        print(f"  ├─ CSO Verdict      : {verdict}")
        print(f"  └─ Reasoning        : {reason}")
        print("="*70)
        self.assertEqual(verdict, "HARD_STOP_20PCT")

if __name__ == '__main__':
    unittest.main(verbosity=2)
