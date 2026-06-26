from src.Journaler import log_trade
import sys

# Usage: python log_trade.py Ticker Side PnL Strategy Deviation EmotionalScore Notes
if __name__ == "__main__":
    if len(sys.argv) < 7:
        print("Usage: python log_trade.py Ticker Side PnL Strategy Deviation EmotionalScore Notes")
        sys.exit(1)
    
    ticker, side, pnl, strategy, dev, emo, notes = sys.argv[1:]
    log_trade(ticker, side, pnl, strategy, dev, emo, notes)
    print("Trade logged successfully.")
