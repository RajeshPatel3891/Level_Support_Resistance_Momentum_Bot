# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (RIVN ACCELERATION MATRIX)
# Target Session: Monday, July 20, 2026
# Active Pool: $17.11 - $17.19 | Spot: $17.45 (+1.75% clear of pool)
# Risk Box: $75.00 - $100.00 Max Premium Risk
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "RIVN260724C00018500"  # July 24, 2026 $18.50 Call
TICKER_PUT  = "RIVN260724P00016500"  # July 24, 2026 $16.50 Put

# 1. BULLISH SCALP: CALL SETUP FROM LIQUIDITY COMPRESSION
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: RIVN recompresses back down into its institutional $17.11-$17.19 band,
    logs structural validation wicks, and snaps back above the tracking VWAP.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 17.35, "close": 17.39, "high": 17.44},
            {"low": 17.22, "close": 17.26, "high": 17.32},
            {"low": 17.15, "close": current_price, "high": 17.28}
        ]
        
    pool_floor = 17.11
    pool_ceiling = 17.19
    
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    current_candle = candles_1m[-1]
    
    vwap_reclaim = (current_candle['close'] >= current_vwap)

    if trigger_zone and vwap_reclaim:
        # Sizing: Target premium ~$0.35 * 20% risk = $0.07/contract risk.
        # 13 contracts * $7.00 = $91.00 total risk box.
        return True, 13
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM ZONE REJECTION
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    pool_ceiling = 17.19
    current_candle = candles_1m[-1]
    
    rejection_zone = (current_price >= pool_ceiling)
    below_vwap = (current_candle['close'] < current_vwap)

    if rejection_zone and below_vwap:
        # Sizing: Target premium ~$0.30 * 20% risk = $0.06/contract risk.
        # 15 contracts * $6.00 = $90.00 total risk box.
        return True, 15
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.50, 2)
    underlying_invalidation = 16.90 if option_type == "CALL" else 17.65
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }
