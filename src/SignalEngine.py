import pandas as pd
import numpy as np

def calculate_indicators(df):
    """
    Calculates Heikin-Ashi, MACD, and 14-period ATR.
    """
    if df is None or df.empty or len(df) < 35:
        return pd.DataFrame()

    df = df.copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    open_s = df['Open'].iloc[:, 0] if isinstance(df['Open'], pd.DataFrame) else df['Open']
    close_s = df['Close'].iloc[:, 0] if isinstance(df['Close'], pd.DataFrame) else df['Close']
    high_s = df['High'].iloc[:, 0] if isinstance(df['High'], pd.DataFrame) else df['High']
    low_s = df['Low'].iloc[:, 0] if isinstance(df['Low'], pd.DataFrame) else df['Low']

    # 1. MACD
    ema12 = close_s.ewm(span=12, adjust=False).mean()
    ema26 = close_s.ewm(span=26, adjust=False).mean()
    df['MACD'] = ema12 - ema26
    df['Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()

    # 2. Heikin-Ashi
    ha_close = (open_s + high_s + low_s + close_s) / 4
    ha_open = np.zeros(len(df))
    ha_open[0] = (open_s.iloc[0] + close_s.iloc[0]) / 2
    for i in range(1, len(df)):
        ha_open[i] = (ha_open[i-1] + ha_close.iloc[i-1]) / 2

    df['HA_Close'] = ha_close
    df['HA_Open'] = ha_open
    df['HA_High'] = np.maximum(high_s, np.maximum(df['HA_Open'], df['HA_Close']))
    df['HA_Low'] = np.minimum(low_s, np.minimum(df['HA_Open'], df['HA_Close']))
    
    # 3. ATR (Average True Range) - 14 Period
    prev_close = close_s.shift(1)
    tr1 = high_s - low_s
    tr2 = (high_s - prev_close).abs()
    tr3 = (low_s - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['ATR'] = tr.rolling(window=14).mean()
    
    return df

def analyze_trade(ticker, price, support, resistance, df):
    """
    Synthesizes DPL levels with HAC + MACD and ATR dynamic exits.
    """
    df = calculate_indicators(df)
    if df is None or df.empty or pd.isna(df['ATR'].iloc[-1]):
        return {"action": "WAIT", "price": price, "reason": "Not enough data for indicators."}

    latest = df.iloc[-1]
    
    actual_close = latest['Close'].iloc[0] if isinstance(latest['Close'], pd.Series) else latest['Close']
    ha_open = latest['HA_Open'].iloc[0] if isinstance(latest['HA_Open'], pd.Series) else latest['HA_Open']
    ha_close = latest['HA_Close'].iloc[0] if isinstance(latest['HA_Close'], pd.Series) else latest['HA_Close']
    ha_low = latest['HA_Low'].iloc[0] if isinstance(latest['HA_Low'], pd.Series) else latest['HA_Low']
    ha_high = latest['HA_High'].iloc[0] if isinstance(latest['HA_High'], pd.Series) else latest['HA_High']
    macd = latest['MACD'].iloc[0] if isinstance(latest['MACD'], pd.Series) else latest['MACD']
    signal = latest['Signal'].iloc[0] if isinstance(latest['Signal'], pd.Series) else latest['Signal']
    atr = latest['ATR'].iloc[0] if isinstance(latest['ATR'], pd.Series) else latest['ATR']

    is_ha_green = ha_close > ha_open
    is_ha_red = ha_close < ha_open
    is_flat_bottom = np.isclose(ha_low, ha_open, atol=0.05)
    is_flat_top = np.isclose(ha_high, ha_open, atol=0.05)
    macd_bullish = macd > signal
    macd_bearish = macd < signal

    # Rule A & C: BUY confirmation at DPL Support
    if actual_close <= (support * 1.01) and actual_close >= (support * 0.99):
        if is_ha_green and is_flat_bottom and macd_bullish:
            tp_price = actual_close + (2.0 * atr)
            sl_price = actual_close - (1.5 * atr)
            return {
                "action": "BUY CONFIRMED",
                "price": actual_close,
                "reason": f"DPL Support Bounce. Volatility Exits -> TP: ${tp_price:.2f} | SL: ${sl_price:.2f}"
            }

    # Rule B: EARLY WARNING EXIT / SHORT confirmation at DPL Resistance
    if actual_close >= (resistance * 0.99) and actual_close <= (resistance * 1.01):
        if is_ha_red and is_flat_top and macd_bearish:
            tp_price = actual_close - (2.0 * atr)
            sl_price = actual_close + (1.5 * atr)
            return {
                "action": "SELL CONFIRMED",
                "price": actual_close,
                "reason": f"DPL Resistance Reject. Volatility Exits -> TP: ${tp_price:.2f} | SL: ${sl_price:.2f}"
            }

    return {"action": "WAIT", "price": actual_close, "reason": "Awaiting HAC/MACD alignment at DPL."}
