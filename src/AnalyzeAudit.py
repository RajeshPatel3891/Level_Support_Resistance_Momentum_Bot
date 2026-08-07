import os
import sys
import csv
import argparse
from datetime import datetime

# Expanded to natively include TSLA
TICKERS = ["SPY", "QQQ", "NVDA", "IWM", "AMZN", "AAPL", "MSFT", "TSLA"]

def analyze_portfolio(date_str="2026-07-07"):
    print("DEBUG: Starting Native Python Audit...")
    print("\n" + "="*50, flush=True)
    print(" HARM.AI // TACTICAL PORTFOLIO AUDIT REPORT ", flush=True)
    print("="*50, flush=True)
    print(f"Analysis Session : {date_str}", flush=True)
    print(f"Metrics Class    : Options Premium Leverage Proxy (10x Mult)", flush=True)
    print("-" * 50, flush=True)
    
    total_trades = 0
    wins = 0
    losses = 0
    net_pnl = 0.0  
    open_positions = 0
    skipped_positions = 0
    
    # Locate files in root or src directories
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    
    for ticker in TICKERS:
        possible_paths = [
            os.path.join(parent_dir, f"{ticker}_audit.csv"),
            os.path.join(current_dir, f"{ticker}_audit.csv"),
            f"{ticker}_audit.csv",
            os.path.join(parent_dir, f"{ticker}_{date_str}_audit.csv"),
            os.path.join(current_dir, f"{ticker}_{date_str}_audit.csv"),
            f"{ticker}_{date_str}_audit.csv"
        ]
        
        target_file = None
        for path in possible_paths:
            if os.path.exists(path):
                target_file = path
                break
                
        if not target_file:
            continue
            
        ticker_trades = 0
        ticker_wins = 0
        ticker_losses = 0
        ticker_pnl = 0.0
        in_trade = False
        entry_price = 0.0
        high_conv_count = 0  # Preserved feature: Tracks total HIGH conviction alerts found
        
        with open(target_file, "r") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            
            for row in reader:
                if not row or len(row) < 5: 
                    continue
                # Layout: Timestamp, Price, Action, Conviction, Result, Notes
                timestamp, price_str, action, conviction, result, notes = row[:6]
                price = float(price_str)
                
                # Feature Preserved: Count occurrences of HIGH Conviction signals
                if conviction == "HIGH":
                    high_conv_count += 1
                
                if action == "ENTER":
                    in_trade = True
                    entry_price = price
                    ticker_trades += 1
                elif action in ["EXIT", "FORCE_CLOSE"]:
                    if in_trade:
                        # Option Premium Leverage Proxy: 5 contracts, $100 premium base ($500 cost), 10x premium multiplier
                        ratio = (price - entry_price) / entry_price if entry_price > 0 else 0.0
                        pnl = 500.0 * ratio * 10.0
                        ticker_pnl += pnl
                        
                        if pnl > 0:
                            ticker_wins += 1
                        else:
                            ticker_losses += 1
                        in_trade = False
                elif action == "SKIP":
                    skipped_positions += 1
                    
            if in_trade:
                open_positions += 1
                
        total_trades += ticker_trades
        wins += ticker_wins
        losses += ticker_losses
        net_pnl += ticker_pnl
        
        # Display ticker level metrics along with the high conviction count
        if ticker_trades > 0:
            ticker_win_rate = (ticker_wins / (ticker_wins + ticker_losses)) * 100 if (ticker_wins + ticker_losses) > 0 else 0.0
            print(f"{ticker:<6} : Trades: {ticker_trades:<3} | Wins: {ticker_wins:<2} | Losses: {ticker_losses:<2} | Win Rate: {ticker_win_rate:>5.2f}% | PnL: ${ticker_pnl:+.2f} | HIGH Conv: {high_conv_count}", flush=True)
        else:
            # Print fallback status if file is present but no trades were active
            print(f"{ticker:<6} : No executions logged during this session. | HIGH Conv: {high_conv_count}", flush=True)
            
    print("-" * 50, flush=True)
    overall_win_rate = (wins / (wins + losses)) * 100 if (wins + losses) > 0 else 0.0
    pnl_sign = "+" if net_pnl >= 0 else "-"
    
    closed_count = wins + losses
    print(f"OVERALL : Closed: {closed_count:<3} | Wins: {wins:<2} | Losses: {losses:<2} | Win Rate: {overall_win_rate:>5.2f}% | PnL: {pnl_sign}${abs(net_pnl):.2f}", flush=True)
    print(f"Active Open      : {open_positions} positions open", flush=True)
    print(f"Capital Bypasses : {skipped_positions} signals skipped")
    print("="*50 + "\n", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unified HARM.AI Portfolio Analyzer")
    parser.add_argument("--date", default="2026-07-07", help="Target evaluation date")
    args = parser.parse_args()
    analyze_portfolio(args.date)
