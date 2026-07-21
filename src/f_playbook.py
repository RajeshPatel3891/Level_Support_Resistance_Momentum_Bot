# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (F ACCELERATION MATRIX)
# Target Session: Monday, July 20, 2026
# Active Pool: $13.88 - $14.01 | Spot: $14.23 (+2.00% clear of pool)
# Risk Box: $75.00 - $100.00 Max Premium Risk
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "F260724C00014500"  # July 24, 2026 $14.50 Call
TICKER_PUT  = "F260724P00013500"  # July 24, 2026 $13.50 Put

# 1. BULLISH SCALP: CALL SETUP ON TARGET POOL COMPRESSION
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: F pulls back from $14.23 to test the top of the pool ($14.01), stabilizes,
    and shows active tick velocity returning north above intraday VWAP.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 14.15, "close": 14.18, "high": 14.22},
            {"low": 14.05, "close": 14.09, "high": 14.14},
            {"low": 13.98, "close": current_price, "high": 14.10}
        ]
        
    pool_floor = 13.88
    pool_ceiling = 14.01
    
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    current_candle = candles_1m[-1]
    
    vwap_reclaim = (current_candle['close'] >= current_vwap)

    if trigger_zone and vwap_reclaim:
        # Sizing: Target premium ~$0.22 * 20% risk = $0.044/contract risk.
        # 20 contracts * $4.40 = $88.00 total risk box.
        return True, 20
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    pool_ceiling = 14.01
    current_candle = candles_1m[-1]
    
    rejection_zone = (current_price >= pool_ceiling)
    below_vwap = (current_candle['close'] < current_vwap)

    if rejection_zone and below_vwap:
        # Sizing: Target premium ~$0.20 * 20% risk = $0.04/contract risk.
        # 22 contracts * $4.00 = $88.00 total risk box.
        return True, 22
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.50, 2)
    underlying_invalidation = 13.75 if option_type == "CALL" else 14.20
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }
