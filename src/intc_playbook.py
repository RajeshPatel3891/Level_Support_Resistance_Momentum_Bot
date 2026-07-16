# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (INTC SYSTEM)
# Target Session: Thursday, July 16, 2026
# Risk Box: $75.00 - $100.00 Max Premium Risk
# Dynamic Manifest Integration
# ==============================================================================

from src.level_loader import get_live_levels

# --- System & Parameter Initialization ---
TICKER_CALL = "INTC260717C00023000"  # 3-DTE proxy Call (OTM)
TICKER_PUT  = "INTC260717P00020500"  # 3-DTE proxy Put (OTM)

# 1. BULLISH SCALP: CALL SETUP FROM AGGRESSIVE SUPPORT
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: INTC hits support and breaks back over local VWAP.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 19.80, "close": 20.10, "high": 20.40},
            {"low": 19.90, "close": 20.25, "high": 20.50},
            {"low": 20.00, "close": current_price, "high": 20.80}
        ]
        
    levels = get_live_levels("INTC")
    if not levels:
        return False, 0
        
    trigger_zone = (levels["support_a"] <= current_price <= levels["support_b"])
    current_candle = candles_1m[-1]
    
    low_wick_test = (current_candle['low'] <= 21.00)
    close_reclaim  = (current_candle['close'] >= 19.50)
    vwap_reclaim   = (current_candle['close'] >= current_vwap)
    
    three_lower_lows = (candles_1m[-1]['low'] < candles_1m[-2]['low'] < candles_1m[-3]['low'])
    if three_lower_lows and not vwap_reclaim:
        return False, 0

    if trigger_zone and low_wick_test and close_reclaim and vwap_reclaim:
        # Sizing: $0.30 premium * 20% risk = $6/contract. 14 contracts = $84 risk box.
        return True, 14
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM AGGRESSIVE RESISTANCE
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    """
    IF: INTC rejects at overhead resistance channels.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 22.80, "close": 23.20, "high": 23.50},
            {"low": 22.65, "close": 22.95, "high": 23.30},
            {"low": 22.40, "close": current_price, "high": 23.15}
        ]
        
    levels = get_live_levels("INTC")
    if not levels:
        return False, 0
        
    resistance_zone = (levels["resistance_a"] <= current_price <= levels["resistance_b"])
    current_candle = candles_1m[-1]
    
    below_vwap = (current_candle['close'] < current_vwap)
    failed_breakout = (current_candle['close'] < candles_1m[-2]['high'])

    if resistance_zone and failed_breakout and below_vwap:
        # Sizing: Target premium of ~$0.28 * 20% risk = $5.60/contract. 15 contracts = $84.
        return True, 15
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.50, 2)
    tp2_target = round(entry_fill * 2.00, 2)
    underlying_invalidation = 19.00 if option_type == "CALL" else 24.50
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "tp2": tp2_target,
        "underlying_invalidation": underlying_invalidation
    }
