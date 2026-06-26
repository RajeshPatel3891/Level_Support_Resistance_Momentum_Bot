import json
import yfinance as yf
from src.Backtester import Backtester

def run_scenarios(ticker):
    print(f"\n--- Analysis for {ticker} ---")
    df = yf.download(ticker, start="2026-06-12", end="2026-06-13", interval="5m")
    dpl = json.load(open("DPL_Levels.json"))
    
    if ticker not in dpl: return

    # FIX: Explicitly convert to scalar using .item()
    high = df['High'].max().item() if hasattr(df['High'].max(), 'item') else df['High'].max()
    low = df['Low'].min().item() if hasattr(df['Low'].min(), 'item') else df['Low'].min()
    
    print(f"DEBUG: {ticker} Price Range: {low:.2f} - {high:.2f} | DPL Support: {dpl[ticker]['support']}")

    tester2 = Backtester(dpl)
    res2 = tester2.run_simulation(ticker, df, tp_pct=0.50, sl_pct=0.50, window_min=30)
    print(f"Scenario 2: {len(res2)} trades | Avg PnL: {sum(t['pnl'] for t in res2)/len(res2):.2%}" if len(res2) > 0 else "Scenario 2: 0 trades")

if __name__ == "__main__":
    for t in ["AAPL", "QQQ", "SPY", "IWM", "NVDA"]:
        run_scenarios(t)
