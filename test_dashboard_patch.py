import sys
import os
import py_compile

print('--- [1/3] Syntax & Compilation Test ---')
try:
    py_compile.compile('dashboard_server.py', doraise=True)
    print('[✓] dashboard_server.py compiled successfully with zero syntax errors!')
except Exception as e:
    print(f'[✗] Syntax Error Detected: {e}')
    sys.exit(1)

print('\n--- [2/3] Import & Helper Function Test ---')
try:
    from dashboard_server import (
        fetch_all_active_dynamo_positions,
        fetch_closed_dynamo_positions,
        fetch_portfolio_state
    )
    print('[✓] Functions imported cleanly from dashboard_server!')
except Exception as e:
    print(f'[✗] Import Failure: {e}')
    sys.exit(1)

print('\n--- [3/3] Direct Function Execution Test ---')
# Test Active Positions
active_trades = fetch_all_active_dynamo_positions()
print(f'[✓] fetch_all_active_dynamo_positions() returned {len(active_trades)} active trades.')
if active_trades:
    sample = active_trades[0]
    print(f"    Sample Active Trade -> Ticker: {sample.get('ticker')}, Strategy: {sample.get('strategy')}, Entry: ${sample.get('entry_price')}")

# Test Closed Positions
closed_trades = fetch_closed_dynamo_positions(selected_date='2026-08-06')
print(f'[✓] fetch_closed_dynamo_positions(2026-08-06) returned {len(closed_trades)} closed trades.')

# Test Full Portfolio State Computation
state = fetch_portfolio_state(selected_date='2026-08-06')
act, cls, float_pnl, closed_pnl, sel_date, start_bal, free_bal, deployed, unsettled = state

print('\n--- Portfolio State Summary ---')
print(f'• Active Trades Count : {len(act)}')
print(f'• Closed Trades Count : {len(cls)}')
print(f'• Deployed Capital    : ${deployed:,.2f}')
print(f'• Settled Free Capital: ${free_bal:,.2f}')
print(f'• Total Floating PnL  : ${float_pnl:,.2f}')
print(f'• Total Closed PnL    : ${closed_pnl:,.2f}')

print('\n[🎉] ALL UNIT TESTS PASSED!')
