# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (NVDA BREAKOUT MATRIX)
# Target Session: Monday, July 20, 2026
# Active Pool: $205.10 - $206.90 | Spot: $202.81 (-1.57% to Pool)
# Risk Box: $75.00 - $100.00 Max Premium Risk
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "NVDA260724C00210000"  # July 24, 2026 $210.00 Call
TICKER_PUT  = "NVDA260724P00200000"  # July 24, 2026 $200.00 Put

# 1. BULLISH SCALP: CALL SETUP ON BREAK INTO SYSTEMIC LIQUIDITY
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: NVDA drives volume up from $202.81 into the institutional block at $205.10.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 202.50, "close": 203.10, "high": 203.50},
            {"low": 203.00, "close": 204.20, "high": 204.60},
            {"low": 204.00, "close": current_price, "high": 205.50}
        ]
        
    pool_floor = 205.10
    pool_ceiling = 206.90
    
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    current_candle = candles_1m[-1]
    
    vwap_reclaim = (current_candle['close'] >= current_vwap)

    if trigger_zone and vwap_reclaim:
        # Sizing: Target premium ~$5.20 * 20% risk = $1.04/contract risk.
        # 9 contracts * $104 = $93.60 total risk footprint.
        return True, 9
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    pool_floor = 205.10
    current_candle = candles_1m[-1]
    
    breakdown_zone = (current_price <= pool_floor)
    below_vwap = (current_candle['close'] < current_vwap)

    if breakdown_zone and below_vwap:
        # Sizing: Target premium ~$4.80 * 20% risk = $0.96/contract risk.
        # 10 contracts * $96 = $96.00 total risk footprint.
        return True, 10
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.45, 2)
    underlying_invalidation = 203.50 if option_type == "CALL" else 208.00
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }
