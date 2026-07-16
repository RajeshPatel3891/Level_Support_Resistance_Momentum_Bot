# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (F STABILITY SYSTEM)
# Target Session: Thursday, July 16, 2026
# Risk Box: $75.00 - $100.00 Max Premium Risk
# Dynamic Manifest Integration
# ==============================================================================

from src.level_loader import get_live_levels

# --- System & Parameter Initialization ---
TICKER_CALL = "F260717C00012000"  # 3-DTE proxy Call (OTM)
TICKER_PUT  = "F260717P00010500"  # 3-DTE proxy Put (OTM)

# 1. BULLISH SCALP: CALL SETUP FROM AGGRESSIVE SUPPORT
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: Ford absorbs sell pressure at support and claims VWAP.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 10.40, "close": 10.60, "high": 10.80},
            {"low": 10.50, "close": 10.70, "high": 10.90},
            {"low": 10.60, "close": current_price, "high": 11.10}
        ]
        
    levels = get_live_levels("F")
    if not levels:
        return False, 0
        
    trigger_zone = (levels["support_a"] <= current_price <= levels["support_b"])
    current_candle = candles_1m[-1]
    
    low_wick_test = (current_candle['low'] <= 11.20)
    close_reclaim  = (current_candle['close'] >= 10.10)
    vwap_reclaim   = (current_candle['close'] >= current_vwap)
    
    three_lower_lows = (candles_1m[-1]['low'] < candles_1m[-2]['low'] < candles_1m[-3]['low'])
    if three_lower_lows and not vwap_reclaim:
        return False, 0

    if trigger_zone and low_wick_test and close_reclaim and vwap_reclaim:
        # Sizing: $0.15 premium * 20% risk = $3/contract. 28 contracts = $84 risk box.
        return True, 28
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM AGGRESSIVE RESISTANCE
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    """
    IF: Ford prints failed breakout structures at overhead limits.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 12.10, "close": 12.40, "high": 12.60},
            {"low": 11.95, "close": 12.25, "high": 12.50},
            {"low": 11.80, "close": current_price, "high": 12.35}
        ]
        
    levels = get_live_levels("F")
    if not levels:
        return False, 0
        
    resistance_zone = (levels["resistance_a"] <= current_price <= levels["resistance_b"])
    current_candle = candles_1m[-1]
    
    below_vwap = (current_candle['close'] < current_vwap)
    failed_breakout = (current_candle['close'] < candles_1m[-2]['high'])

    if resistance_zone and failed_breakout and below_vwap:
        # Sizing: Target premium of ~$0.14 * 20% risk = $2.80/contract. 30 contracts = $84.
        return True, 30
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.50, 2)
    tp2_target = round(entry_fill * 2.00, 2)
    underlying_invalidation = 9.80 if option_type == "CALL" else 13.50
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "tp2": tp2_target,
        "underlying_invalidation": underlying_invalidation
    }
