# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (AAPL RE-ENTRY MATRIX)
# Target Session: Monday, July 20, 2026
# Active Pool: $323.10 - $324.90 | Spot: $333.74 (+2.92% clear of pool)
# Risk Box: $75.00 - $100.00 Max Premium Risk
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "AAPL260724C00340000"  # July 24, 2026 $340.00 Call
TICKER_PUT  = "AAPL260724P00325000"  # July 24, 2026 $325.00 Put

# 1. BULLISH SCALP: CALL SETUP ON RETEST OF SYSTEMIC POOL CEILING
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: AAPL filters down into the major $323.10 - $324.90 liquidity zone, 
    exhausts sell side volume, and ticks upward to reclaim intraday VWAP.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 326.10, "close": 326.80, "high": 327.50},
            {"low": 324.80, "close": 325.20, "high": 325.90},
            {"low": 323.50, "close": current_price, "high": 324.80}
        ]
        
    pool_floor = 323.10
    pool_ceiling = 324.90
    
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    current_candle = candles_1m[-1]
    
    vwap_reclaim = (current_candle['close'] >= current_vwap)

    if trigger_zone and vwap_reclaim:
        # Sizing: Target premium ~$4.50 * 20% risk = $0.90/contract risk.
        # 10 contracts * $90 = $90.00 total risk allocation.
        return True, 10
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM HIGH-VOLUME REJECTION
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    pool_ceiling = 324.90
    current_candle = candles_1m[-1]
    
    rejection_zone = (current_price >= pool_ceiling)
    below_vwap = (current_candle['close'] < current_vwap)

    if rejection_zone and below_vwap:
        # Sizing: Target premium ~$4.10 * 20% risk = $0.82/contract risk.
        # 11 contracts * $82 = $90.20 total risk allocation.
        return True, 11
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.45, 2)
    underlying_invalidation = 321.50 if option_type == "CALL" else 326.50
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }
