import csv
import glob
import os

def reconcile():
    print(f"\n{'='*60}")
    print(f" HARM.AI // PRODUCTION ALERT RECONCILIATION ")
    print(f"{'='*60}")
    print(f"{'Ticker':<10} | {'Trades':<8} | {'Win Rate':<10} | {'PnL':<10}")
    print(f"{'-'*60}")

    overall_pnl = 0.0
    overall_wins = 0
    overall_trades = 0

    for filepath in glob.glob("*_audit.csv"):
        ticker = filepath.split('_')[0]
        if ticker not in ["SPY", "QQQ", "NVDA", "IWM", "AMZN", "AAPL", "MSFT", "TSLA"]: continue
        
        trades = []
        entry = None
        
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)
            for ts, price, action, conv, res, notes in reader:
                price = float(price)
                if action == "ENTER":
                    entry = {"ts": ts, "price": price}
                elif action == "EXIT" and entry:
                    # Calculate PnL for this specific production alert
                    pnl = 500.0 * ((price - entry['price']) / entry['price']) * 10.0
                    if res == "STOP_LOSS": pnl = -abs(pnl)
                    
                    trades.append(pnl)
                    entry = None
        
        if trades:
            wins = len([p for p in trades if p > 0])
            total = len(trades)
            ticker_pnl = sum(trades)
            overall_pnl += ticker_pnl
            overall_wins += wins
            overall_trades += total
            
            print(f"{ticker:<10} | {total:<8} | {(wins/total)*100:>8.1f}% | ${ticker_pnl:>+8.2f}")

    print(f"{'-'*60}")
    wr = (overall_wins / overall_trades) * 100 if overall_trades > 0 else 0
    print(f"{'TOTAL':<10} | {overall_trades:<8} | {wr:>8.1f}% | ${overall_pnl:>+8.2f}")
    print(f"{'='*60}\n")

reconcile()
