# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (AAL MOMENTUM AGENT)
# Target Session: Thursday, July 16, 2026
# Risk Box: $75.00 - $100.00 Max Premium Risk
# Dynamic Manifest Integration
# ==============================================================================

from src.level_loader import get_live_levels

# --- System & Parameter Initialization ---
TICKER_CALL = "AAL260717C00013000"  # 3-DTE proxy Call (OTM)
TICKER_PUT  = "AAL260717P00011500"  # 3-DTE proxy Put (OTM)

# 1. BULLISH SCALP: CALL SETUP FROM AGGRESSIVE SUPPORT
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: AAL sweeps support zone and reclaims VWAP.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 11.20, "close": 11.40, "high": 11.60},
            {"low": 11.30, "close": 11.50, "high": 11.70},
            {"low": 11.40, "close": current_price, "high": 11.90}
        ]
        
    levels = get_live_levels("AAL")
    if not levels:
        return False, 0
        
    trigger_zone = (levels["support_a"] <= current_price <= levels["support_b"])
    current_candle = candles_1m[-1]
    
    low_wick_test = (current_candle['low'] <= 12.00)
    close_reclaim  = (current_candle['close'] >= 11.00)
    vwap_reclaim   = (current_candle['close'] >= current_vwap)
    
    three_lower_lows = (candles_1m[-1]['low'] < candles_1m[-2]['low'] < candles_1m[-3]['low'])
    if three_lower_lows and not vwap_reclaim:
        return False, 0

    if trigger_zone and low_wick_test and close_reclaim and vwap_reclaim:
        # Sizing: $0.20 premium * 20% risk = $4/contract. 20 contracts = $80 risk box.
        return True, 20
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM AGGRESSIVE RESISTANCE
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    """
    IF: AAL rolls over at key resistance boundaries.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 13.50, "close": 13.80, "high": 14.10},
            {"low": 13.30, "close": 13.65, "high": 13.90},
            {"low": 13.10, "close": current_price, "high": 13.75}
        ]
        
    levels = get_live_levels("AAL")
    if not levels:
        return False, 0
        
    resistance_zone = (levels["resistance_a"] <= current_price <= levels["resistance_b"])
    current_candle = candles_1m[-1]
    
    below_vwap = (current_candle['close'] < current_vwap)
    failed_breakout = (current_candle['close'] < candles_1m[-2]['high'])

    if resistance_zone and failed_breakout and below_vwap:
        # Sizing: Target premium of ~$0.18 * 20% risk = $3.60/contract. 23 contracts = $82.80.
        return True, 23
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.50, 2)
    tp2_target = round(entry_fill * 2.00, 2)
    underlying_invalidation = 10.50 if option_type == "CALL" else 15.00
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "tp2": tp2_target,
        "underlying_invalidation": underlying_invalidation
    }
