import yfinance as yf

def get_market_data(ticker):
    """
    Fetches the latest 5-minute OHLC data for the ticker.
    """
    stock = yf.Ticker(ticker)
    # Get the last 1 day of 5-minute data
    df = stock.history(period="1d", interval="5m")
    
    if df.empty:
        return None
        
    latest_price = df['Close'].iloc[-1]
    return {
        "current_price": latest_price,
        "history": df
    }
