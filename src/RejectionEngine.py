import pandas as pd
import talib # Using TA-Lib for pattern recognition

def check_proximity(current_price, resistance, buffer_pct=0.003):
    """Flags if price is within buffer of resistance."""
    return current_price >= (resistance * (1 - buffer_pct))

def detect_rejection(df):
    """
    Scans for bearish reversal patterns (e.g., Shooting Star or Bearish Engulfing)
   
    """
    # Using TA-Lib to identify patterns
    patterns = {
        'ShootingStar': talib.CDLSHOOTINGSTAR(df['Open'], df['High'], df['Low'], df['Close']),
        'Engulfing': talib.CDLENGULFING(df['Open'], df['High'], df['Low'], df['Close'])
    }
    
    # Check the latest candle for a pattern
    latest = {k: v.iloc[-1] for k, v in patterns.items()}
    return latest

def analyze_proximity(ticker, current_price, resistance, df):
    if check_proximity(current_price, resistance):
        patterns = detect_rejection(df)
        if any(patterns.values()):
            return "REJECTION_CONFIRMED"
        return "PROXIMITY_ALERT"
    return "WAIT"
