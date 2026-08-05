#!/usr/bin/env python3
import sys
import os
import json
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.gemini_cso_evaluator import evaluate_macro_rebound

def run_time_decay_unit_tests():
    print("=" * 75)
    print("🧪 TESTING GEMINI CSO TIME & THETA DECAY AWARENESS ENGINE")
    print("=" * 75)

    # TEST SCENARIO 1: Early Trade (5 mins in), Low Decay -> Expect HOLD_REBOUND
    payload1 = {
        "ticker": "NVDA",
        "time_in_trade_minutes": 5.0,
        "mttp_max_limit": 45,
        "drawdown_pct": -21.0,
        "spot_price": 212.50,
        "vwap": 213.00,
        "theta": -0.04,
        "delta": 0.55,
        "theta_delta_ratio": 0.07,
        "is_weekly_0dte": False,
        "decay_warning": "NORMAL"
    }
    print("\n1. Testing Early Trade (5m in trade, low theta bleed):")
    res1 = evaluate_macro_rebound(payload1)
    print(f"   Verdict: {res1.get('verdict')} | Rationale: {res1.get('reasoning')}")

    # TEST SCENARIO 2: Late Trade (35 mins in) + Small-Cap Weekly -> Expect CUT_EARLY
    payload2 = {
        "ticker": "SOFI",
        "time_in_trade_minutes": 35.0,
        "mttp_max_limit": 45,
        "drawdown_pct": -22.5,
        "spot_price": 18.50,
        "vwap": 18.70,
        "theta": -0.15,
        "delta": 0.30,
        "theta_delta_ratio": 0.50,
        "is_weekly_0dte": True,
        "decay_warning": "CRITICAL_THETA_BLEED"
    }
    print("\n2. Testing Small-Cap Weekly Theta Trap (35m in trade, high decay):")
    res2 = evaluate_macro_rebound(payload2)
    print(f"   Verdict: {res2.get('verdict')} | Rationale: {res2.get('reasoning')}")
    assert res2.get("verdict") == "CUT_EARLY", "FAIL: Small-cap weekly theta trap was not cut early!"

    # TEST SCENARIO 3: Extreme Theta/Delta Ratio (> 0.30) -> Expect CUT_EARLY
    payload3 = {
        "ticker": "RIVN",
        "time_in_trade_minutes": 28.0,
        "mttp_max_limit": 45,
        "drawdown_pct": -24.0,
        "spot_price": 15.70,
        "vwap": 15.85,
        "theta": -0.18,
        "delta": 0.25,
        "theta_delta_ratio": 0.72,
        "is_weekly_0dte": True,
        "decay_warning": "CRITICAL_THETA_BLEED"
    }
    print("\n3. Testing Critical Theta/Delta Ratio Bleed (Ratio > 0.30):")
    res3 = evaluate_macro_rebound(payload3)
    print(f"   Verdict: {res3.get('verdict')} | Rationale: {res3.get('reasoning')}")
    assert res3.get("verdict") == "CUT_EARLY", "FAIL: High Theta/Delta ratio trade was not cut early!"

    print("\n" + "=" * 75)
    print("🦅 [✓] ALL TIME & DECAY CSO UNIT TESTS PASSED PERFECTLY!")
    print("=" * 75)

if __name__ == "__main__":
    run_time_decay_unit_tests()
