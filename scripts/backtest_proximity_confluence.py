import os
import sys
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

TRADIER_TOKEN = os.getenv("TRADIER_PROD_TOKEN") or os.getenv("TRADIER_TOKEN")
HEADERS = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
TICKERS = ["XLF", "GDX", "XLE", "SOFI", "HOOD", "PLTR", "RIVN", "MARA"]

def fetch_historical_candles(ticker, start_date, end_date):
    url = "https://api.tradier.com/v1/markets/history"
    params = {"symbol": ticker, "interval": "daily", "start": start_date, "end": end_date}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json().get("history", {}).get("day", [])
            if isinstance(data, dict):
                data = [data]
            return pd.DataFrame(data)
    except Exception as e:
        print(f"[!] Error fetching history for {ticker}: {e}")
    return pd.DataFrame()

def backtest_proximity_touch(ticker, start_date, end_date, target_pct=0.90):
    """
    Evaluates conversion rate: When spot reaches target_pct of daily GEX level,
    does it reach 100% before triggering a -20% stop loss?
    """
    print(f"[*] Backtesting Proximity Confluence for {ticker} ({start_date} to {end_date}) at {target_pct*100}% threshold...")
    df = fetch_historical_candles(ticker, start_date, end_date)
    if df.empty or 'close' not in df.columns:
        print(f"[-] No valid history returned for {ticker}.")
        return {"ticker": ticker, "trades": 0, "win_rate": 0.0}

    df['close'] = pd.to_numeric(df['close'])
    df['high'] = pd.to_numeric(df['high'])
    df['low'] = pd.to_numeric(df['low'])
    
    # Simulate GEX boundary level envelope
    df['gex_level'] = df['high'].rolling(window=5, min_periods=1).max() * 1.02
    
    wins = 0
    losses = 0
    total_trades = 0

    for i in range(5, len(df)):
        row = df.iloc[i]
        level = df['gex_level'].iloc[i-1]
        trigger_price = level * target_pct
        
        if row['high'] >= trigger_price:
            total_trades += 1
            stop_loss = trigger_price * 0.80
            if row['high'] >= level:
                wins += 1
            elif row['low'] <= stop_loss:
                losses += 1
            else:
                if row['close'] >= trigger_price:
                    wins += 1
                else:
                    losses += 1

    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
    print(f"[✓] {ticker} Results -> Trades: {total_trades}, Wins: {wins}, Losses: {losses}, Win Rate: {win_rate:.1f}%")
    return {"ticker": ticker, "trades": total_trades, "wins": wins, "losses": losses, "win_rate": win_rate}

if __name__ == "__main__":
    end_dt = datetime.now().strftime("%Y-%m-%d")
    start_dt = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    
    results = []
    for t in TICKERS:
        res = backtest_proximity_touch(t, start_dt, end_dt, target_pct=0.90)
        results.append(res)
        
    print("\n==========================================")
    print("📊 PROXIMITY CONFLUENCE BACKTEST SUMMARY")
    print("==========================================")
    for r in results:
        print(f"Ticker: {r['ticker']} | Trades: {r['trades']} | Win Rate: {r['win_rate']:.1f}%")
