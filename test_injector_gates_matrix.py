#!/usr/bin/env python3
"""
HARM.AI // FULL ENTRY GATE & 4% SPREAD INJECTION MATRIX TESTER
===============================================================================
Tests 4 entry gate scenarios offline:
1. Tight Spread Option (2.0% Spread)         -> PASS (Gate 3 Allowed -> Mock Fill)
2. Wide Spread Option (8.5% Spread)          -> FAIL (Gate 3 Rejection)
3. Cheap Option Penny Spread ($0.20 / $0.02) -> PASS (Gate 3 Penny Bypass -> Mock Fill)
4. VWAP Misalignment (Spot < VWAP on CALL)   -> FAIL (Gate 2 Rejection)
"""

import os
import json
import src.smart_cso_injector as sci

# Mock market data lookup table with high-proximity targets
MOCK_MARKET_STATE = {
    "GATE_TIGHT": {
        "spot": 100.0, "vwap": 99.5, "target": 100.20,
        "opt": {"symbol": "TIGHT260904C00100000", "bid": 2.00, "ask": 2.04, "open_interest": 500, "volume": 200, "option_type": "call"},
        "desc": "Tight Spread Option (2.0% Spread)"
    },
    "GATE_WIDE": {
        "spot": 100.0, "vwap": 99.5, "target": 100.20,
        "opt": {"symbol": "WIDE260904C00100000", "bid": 2.00, "ask": 2.17, "open_interest": 500, "volume": 200, "option_type": "call"},
        "desc": "Wide Spread Option (8.5% Spread)"
    },
    "GATE_CHEAP": {
        "spot": 50.0, "vwap": 49.5, "target": 50.10,
        "opt": {"symbol": "CHEAP260904C00050000", "bid": 0.20, "ask": 0.22, "open_interest": 500, "volume": 200, "option_type": "call"},
        "desc": "Cheap Sub-$0.50 Option ($0.02 Penny Spread)"
    },
    "GATE_VWAP": {
        "spot": 99.0, "vwap": 100.0, "target": 99.20, # Spot 99.0 < VWAP 100.0 -> REJECT CALL
        "opt": {"symbol": "VWAP260904C00100000", "bid": 2.00, "ask": 2.04, "open_interest": 500, "volume": 200, "option_type": "call"},
        "desc": "VWAP Misalignment (Spot < VWAP on CALL)"
    }
}

# Override quote fetchers and blocking loops for offline test run
def mock_get_live_quote(symbol):
    if symbol in MOCK_MARKET_STATE:
        state = MOCK_MARKET_STATE[symbol]
        return {"last": state["spot"], "change_percentage": 0.0}
    elif symbol in ["SPY", "QQQ"]:
        return {"last": 560.0, "change_percentage": 0.0}
    return {}

def mock_search_smart_option_chain(ticker, direction="CALL", spot_price=0.0):
    if ticker in MOCK_MARKET_STATE:
        return MOCK_MARKET_STATE[ticker]["opt"]
    return None

def mock_execute_strict_tradier_order(occ_symbol, underlying, side, quantity=1, max_wait_seconds=5, execution_tag="SCJ"):
    print(f"  [⚡ ORDER EXECUTION] Mock Fill Triggered for {occ_symbol} @ MID")
    return True, 2.02, "MOCK_ORDER_12345"

def mock_log_trade_dual_db(*args, **kwargs):
    print(f"  [✓ DB INGESTION] Active trade receipt written to SQLite & DynamoDB.")

def mock_monitor_live_exit_telemetry(ticker):
    print(f"  [📡 MOCK STREAM] Live exit watch loop bypassed for test completion.")

sci.get_live_quote = mock_get_live_quote
sci.search_smart_option_chain = mock_search_smart_option_chain
sci.execute_strict_tradier_order = mock_execute_strict_tradier_order
sci.log_trade_dual_db = mock_log_trade_dual_db
sci.monitor_live_exit_telemetry = mock_monitor_live_exit_telemetry
sci.is_valid_time_of_day_window = lambda: True
sci.check_active_position_exists = lambda ticker, tenant_id='COMPANY_A': False
sci.validate_reentry_eligibility = lambda ticker, db_path=None: True

def run_gate_suite():
    print("=" * 95)
    print("🧪 HARM.AI // FULL ENTRY GATE & 4% SPREAD INJECTION MATRIX EVALUATION")
    print("=" * 95)

    for ticker, data in MOCK_MARKET_STATE.items():
        print(f"\n▶ TESTING SCENARIO: {data['desc']} ({ticker})")
        print("-" * 75)
        
        temp_levels = {
            ticker: {
                "spot": data["spot"],
                "vwap": data["vwap"],
                "target": data["target"],
                "execution_armed": True
            }
        }
        
        with open("trading_levels.json", "w") as f:
            json.dump(temp_levels, f)

        sci.smart_cso_scout_and_execute(force_ticker=ticker, direction_override="CALL")

    print("\n" + "=" * 95)
    print("🧹 [CLEANUP] Resetting manifest file...")
    if os.path.exists("trading_levels.json"):
        os.remove("trading_levels.json")
    print("=" * 95)

if __name__ == "__main__":
    run_gate_suite()
