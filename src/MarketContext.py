import yfinance as yf
import pandas as pd

def get_market_context():
    """
    Fetches real-time snapshots of VIX, SPY, and QQQ to build automated quantitative context.
    """
    try:
        # Fetch tickers with a 1-day period and 5-minute interval for recent trends
        tickers = yf.Tickers('^VIX SPY QQQ')
        
        # Get historical data for the last 2 days to calculate today's change from prior close
        vix_hist = tickers.tickers['^VIX'].history(period='2d')
        spy_hist = tickers.tickers['SPY'].history(period='2d')
        qqq_hist = tickers.tickers['QQQ'].history(period='2d')
        
        if len(vix_hist) < 2 or len(spy_hist) < 2 or len(qqq_hist) < 2:
            return "Context: Market data snapshot incomplete."

        # Calculate daily percentage changes
        vix_change = ((vix_hist['Close'].iloc[-1] - vix_hist['Close'].iloc[-2]) / vix_hist['Close'].iloc[-2]) * 100
        spy_change = ((spy_hist['Close'].iloc[-1] - spy_hist['Close'].iloc[-2]) / spy_hist['Close'].iloc[-2]) * 100
        qqq_change = ((qqq_hist['Close'].iloc[-1] - qqq_hist['Close'].iloc[-2]) / qqq_hist['Close'].iloc[-2]) * 100
        
        current_vix = vix_hist['Close'].iloc[-1]

        # Determine market sentiment indicators
        vix_status = "dropping" if vix_change < 0 else "spiking"
        tech_status = "stronger than broader market" if qqq_change > spy_change else "underperforming SPY"
        
        context_str = (
            f"--- Automated Market Context ---\n"
            f"• VIX is {vix_status} today at {current_vix:.2f} ({vix_change:+.2f}%)\n"
            f"• SPY: {spy_change:+.2f}% | QQQ: {qqq_change:+.2f}%\n"
            f"• Sentiment: Tech is {tech_status}."
        )
        return context_str

    except Exception as e:
        return f"--- Automated Market Context ---\n• Error fetching yfinance data: {str(e)}"

if __name__ == "__main__":
    print(get_market_context())
