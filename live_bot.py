import json
import time
import pandas as pd
import yfinance as yf
from datetime import datetime
from src.SignalEngine import analyze_trade
from src.AlertManager import send_discord_alert
from src.RejectionEngine import analyze_proximity

with open('DPL_Levels.json', 'r') as f:
    dpl_levels = json.load(f)

tickers = list(dpl_levels.keys())
last_alerted = {ticker: None for ticker in tickers}

print(f"[{datetime.now().strftime('%H:%M:%S')}] Harmonized AI Sentry (Proximity Enabled) initialized.")

while True:
    try:
        data = yf.download(tickers, period="5d", interval="60m", progress=False)
        for ticker in tickers:
            levels = dpl_levels.get(ticker)
            if not levels: continue
            
            df = data.xs(ticker, axis=1, level=1) if isinstance(data.columns, pd.MultiIndex) else data
            current_price = float(df['Close'].iloc[-1])
            
            # 1. Check for Proximity/Rejection
            prox_signal = analyze_proximity(ticker, current_price, levels['resistance'], df)
            
            if prox_signal != 'WAIT':
                current_time = datetime.now().strftime("%Y-%m-%d %H")
                if last_alerted[ticker] != f"{prox_signal}_{current_time}":
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ALERT: {ticker} - {prox_signal}")
                    send_discord_alert(ticker, prox_signal, current_price, "Resistance interaction detected.")
                    last_alerted[ticker] = f"{prox_signal}_{current_time}"

            # 2. Check for original DPL bounce signals
            signal = analyze_trade(ticker, current_price, levels['support'], levels['resistance'], df)
            if signal['action'] != 'WAIT':
                # (Keep your existing alert logic here)
                pass
                    
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan complete. Sleeping...")
    except Exception as e:
        print(f"Sentry Error: {e}")
    time.sleep(300)
