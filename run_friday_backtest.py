import yfinance as yf
import pandas as pd
from src.Backtester import Backtester

def adjust_for_gaps(ticker, df, static_levels):
    if df.empty:
        return static_levels
        
    day_open = df['Open'].iloc[0]
    support = static_levels['support']
    resistance = static_levels['resistance']
    spread = resistance - support
    
    # Logic: If price opens completely below Support (Gap Down)
    if day_open < support:
        new_sup = day_open - (spread * 0.5)
        new_res = day_open + (spread * 0.5)
        print(f"  [!] {ticker} Gapped Down (Open: ${day_open:.2f}). Shifted Zone: ${new_sup:.2f} -> ${new_res:.2f}")
        return {"support": new_sup, "resistance": new_res}
        
    # Logic: If price opens completely above Resistance (Gap Up)
    elif day_open > resistance:
        new_sup = day_open - (spread * 0.5)
        new_res = day_open + (spread * 0.5)
        print(f"  [!] {ticker} Gapped Up (Open: ${day_open:.2f}). Shifted Zone: ${new_sup:.2f} -> ${new_res:.2f}")
        return {"support": new_sup, "resistance": new_res}
        
    # If it opens inside the expected zone, keep the analyst levels
    return static_levels

def main():
    print("=== Running Historical Backtest: Dynamic Gap Detection ===")
    
    friday_levels = {
        "SPY": {"support": 748.0, "resistance": 755.0},
        "QQQ": {"support": 733.50, "resistance": 743.0},
        "IWM": {"support": 296.66, "resistance": 300.0},
        "AAPL": {"support": 292.0, "resistance": 296.50},
        "NVDA": {"support": 200.0, "resistance": 210.50},
        "TSLA": {"support": 409.50, "resistance": 418.0}
    }
    
    tickers = list(friday_levels.keys())
    
    for ticker in tickers:
        print(f"\nProcessing data for {ticker}...")
        
        df = yf.download(
            ticker, 
            start="2026-06-12", 
            end="2026-06-13", 
            interval="5m", 
            progress=False
        )
        
        if df.empty:
            print(f"No data retrieved for {ticker}. Skipping.")
            continue
            
        # Flatten MultiIndex columns immediately
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # Apply the Dynamic Gap Adjuster
        dynamic_levels = adjust_for_gaps(ticker, df, friday_levels[ticker])
        
        # Initialize Backtester with the dynamically adjusted levels for this specific ticker
        backtester = Backtester(dpl_levels={ticker: dynamic_levels})
        
        results = backtester.run_simulation(ticker=ticker, df=df)
        
        print(f"Total Trades Executed for {ticker}: {len(results)}")
        for trade in results:
            print(f"  -> {trade['action']} at {trade['start_time']} | Entry: {trade['entry_price']:.2f} | PnL: {trade['pnl']*100:.2f}%")

if __name__ == "__main__":
    main()
