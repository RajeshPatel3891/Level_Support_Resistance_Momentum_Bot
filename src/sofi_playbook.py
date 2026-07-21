# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (SOFI POOL ACCELERATION)
# Target Session: Monday, July 20, 2026
# Active Pool: $17.11 - $17.19 | Spot: $17.28 (+0.75% to Pool)
# Risk Box: $75.00 - $100.00 Max Premium Risk
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "SOFI260724C00018000"  # July 24, 2026 $18.00 Call
TICKER_PUT  = "SOFI260724P00016500"  # July 24, 2026 $16.50 Put

# 1. BULLISH SCALP: CALL SETUP ON COMPRESSION RECLAIM
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: SOFI ticks down into the $17.11 - $17.19 pool structure, finds base stability,
    and springs back up over active short-term VWAP.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 17.20, "close": 17.25, "high": 17.30},
            {"low": 17.15, "close": 17.18, "high": 17.22},
            {"low": 17.12, "close": current_price, "high": 17.24}
        ]
        
    pool_floor = 17.11
    pool_ceiling = 17.19
    
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    current_candle = candles_1m[-1]
    
    vwap_reclaim = (current_candle['close'] >= current_vwap)

    if trigger_zone and vwap_reclaim:
        # Sizing: Target premium ~$0.32 * 20% risk = $0.064/contract risk.
        # 14 contracts * $6.40 = $89.60 total risk footprint.
        return True, 14
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    pool_ceiling = 17.19
    current_candle = candles_1m[-1]
    
    rejection_zone = (current_price >= pool_ceiling)
    below_vwap = (current_candle['close'] < current_vwap)

    if rejection_zone and below_vwap:
        # Sizing: Target premium ~$0.28 * 20% risk = $0.056/contract risk.
        # 16 contracts * $5.60 = $89.60 total risk footprint.
        return True, 16
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.50, 2)
    underlying_invalidation = 16.95 if option_type == "CALL" else 17.40
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }
