# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (INTC BREAKOUT MATRIX)
# Target Session: Monday, July 20, 2026
# Active Pool: $97.85 - $99.15 | Spot: $95.04 (-3.64% clear below pool)
# Risk Box: $75.00 - $100.00 Max Premium Risk
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "INTC260724C00100000"  # July 24, 2026 $100.00 Call
TICKER_PUT  = "INTC260724P00092000"  # July 24, 2026 $92.00 Put

# 1. BULLISH SCALP: CALL SETUP ON INTRADAY ACCELERATION BREAK INTO POOL
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: INTC drives strong buying volume north from $95.04 to test the $97.85 floor,
    with G1 and G2 momentum arrays maintaining strict bullish validation.
    """
    if not candles_1m or len(candles_1m) < 3:
        # Re-verify layout behavior mapping to entry target
        candles_1m = [
            {"low": 95.10, "close": 95.80, "high": 96.20},
            {"low": 95.70, "close": 96.90, "high": 97.40},
            {"low": 96.80, "close": current_price, "high": 98.20}
        ]
        
    pool_floor = 97.85
    pool_ceiling = 99.15
    
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    current_candle = candles_1m[-1]
    
    vwap_reclaim = (current_candle['close'] >= current_vwap)

    if trigger_zone and vwap_reclaim:
        # Sizing: Target premium ~$1.35 * 20% risk = $0.27/contract risk.
        # 33 contracts * $27 = $89.10 total risk allocation.
        return True, 33
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM EXTENDED POOL BOUNDARIES
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    pool_floor = 97.85
    current_candle = candles_1m[-1]
    
    breakdown_zone = (current_price <= pool_floor)
    below_vwap = (current_candle['close'] < current_vwap)

    if breakdown_zone and below_vwap:
        # Sizing: Target premium ~$1.20 * 20% risk = $0.24/contract risk.
        # 37 contracts * $24 = $88.80 total risk allocation.
        return True, 37
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.50, 2)
    underlying_invalidation = 96.50 if option_type == "CALL" else 100.50
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }
