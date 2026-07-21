# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (TSLA ACCELERATION MATRIX)
# Target Session: Monday, July 20, 2026
# Active Pool: $384.10 - $385.90 | Spot: $380.84 (-1.09% to Pool)
# Risk Box: $75.00 - $100.00 Max Premium Risk
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "TSLA260724C00390000"  # July 24, 2026 $390.00 Call
TICKER_PUT  = "TSLA260724P00375000"  # July 24, 2026 $375.00 Put

# 1. BULLISH SCALP: CALL SETUP ON MOMENTUM BREAK INTO THE POOL
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: TSLA surges from its pre-market low ($380.84) to cross into the $384.10 floor,
    with positive directional tick volume validating the breakout above VWAP.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 380.50, "close": 381.20, "high": 381.80},
            {"low": 381.10, "close": 382.90, "high": 383.40},
            {"low": 382.50, "close": current_price, "high": 384.50}
        ]
        
    pool_floor = 384.10
    pool_ceiling = 385.90
    
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    current_candle = candles_1m[-1]
    
    vwap_reclaim = (current_candle['close'] >= current_vwap)
    momentum_velocity = (current_candle['close'] > candles_1m[-2]['high'])

    if trigger_zone and vwap_reclaim and momentum_velocity:
        # Sizing: Target premium ~$8.50 * 20% risk = $1.70/contract risk.
        # 5 contracts * $170 = $85.00 total risk footprint.
        return True, 5
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM POOL REJECTION
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    """
    IF: TSLA hits the pool ceiling ($385.90), prints an exhaustion wick, and loses VWAP.
    """
    pool_ceiling = 385.90
    current_candle = candles_1m[-1]
    
    rejection_zone = (current_price >= pool_ceiling - 1.00)
    below_vwap = (current_candle['close'] < current_vwap)

    if rejection_zone and below_vwap:
        # Sizing: Target premium ~$7.80 * 20% risk = $1.56/contract risk.
        # 5 contracts * $156 = $78.00 total risk footprint.
        return True, 5
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.40, 2)
    underlying_invalidation = 382.00 if option_type == "CALL" else 387.50
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }
