import csv
from datetime import datetime
import os

def log_trade(ticker, side, pnl, strategy, dev, emo, notes):
    file_exists = os.path.isfile('TradeLog.csv')
    with open('TradeLog.csv', 'a', newline='') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['Timestamp', 'Ticker', 'Side', 'PnL', 'Strategy', 'Deviation', 'EmotionalScore', 'Notes'])
        writer.writerow([datetime.now().strftime("%Y-%m-%d %H:%M"), ticker, side, pnl, strategy, dev, emo, notes])
