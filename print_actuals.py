import asyncio
from dashboard_server import fetch_portfolio_state

trades, closed, total_floating, total_closed, date, start_bal, settled, deployed, unsettled = fetch_portfolio_state()

print("=" * 80)
print(f"📊 LIVE LOCAL DASHBOARD OUTPUT | DEPLOYED: ${deployed:,.2f} | FLOATING PNL: {total_floating}")
print("=" * 80)
print(f"{'TICKER':<8} {'DIR':<6} {'LIVE SPOT':<10} {'COST':<8} {'SHARES':<8} {'CALC PNL':<12} {'PNL %':<10}")
print("-" * 80)

for t in trades:
    tkr = t.get('ticker', 'N/A')
    direction = t.get('direction', 'CALL')
    spot = t.get('price', '0.00')
    cost = t.get('cost', '0.00')
    shares = t.get('shares', 1.0)
    pnl = t.get('dollar_pnl', '$0.00')
    pnl_pct = t.get('pnl_pct', '0.0%')
    print(f"{tkr:<8} {direction:<6} ${spot:<9} ${cost:<7} {shares:<8} {pnl:<12} {pnl_pct:<10}")

print("=" * 80)
