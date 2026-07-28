import pprint
from dashboard_server import fetch_portfolio_state

active_trades, db_closed, total_pnl, total_closed_pnl, *_ = fetch_portfolio_state()

print("=== LIVE ACTIVE TRADES OUTPUT ===")
for trade in active_trades:
    print(f"Ticker: {trade.get('ticker')}")
    print(f"  Live Stock Price: ${trade.get('price')} (Ref Spot: ${trade.get('spot_price')})")
    print(f"  Entry Basis: ${trade.get('basis')}")
    print(f"  Calculated Dollar PnL: {trade.get('dollar_pnl')} ({trade.get('pnl_pct')})")

print(f"\n=== TOTAL OPEN FLOATING PNL: ${total_pnl:,.2f} ===")
