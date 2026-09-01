#!/usr/bin/env python3
"""
HARM.AI // OFFLINE EVALUATION TESTER
===============================================================================
Mocks a live option quote ($2.12 / +6% gain) to verify gex_exit_monitor.py's
dynamic stop loss ladder logic on STREAM_TEST_NVDA.
"""

import os
import src.gex_exit_monitor as gem

# Ensure ACTIVE_TICKERS doesn't block NVDA
os.environ["ACTIVE_TICKERS"] = "NVDA"

# Mock live quote fetcher to simulate market open quote ($2.12 / +6% gain)
def mock_get_live_quote(occ_symbol):
    return 2.12, "https://sandbox.tradier.com/v1"

# Monkey-patch mock quote engine
gem.get_live_quote = mock_get_live_quote

print("=" * 80)
print("🧪 TESTING SINGLE-PASS EVALUATION (MOCKED LIVE QUOTE: $2.12 / +6.0%)")
print("=" * 80)

gem.evaluate_gex_exits()

print("=" * 80)
