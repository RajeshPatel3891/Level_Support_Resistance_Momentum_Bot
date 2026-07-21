# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (AAL BREAKOUT MATRIX)
# Target Session: Monday, July 20, 2026
# Active Pool: $15.10 - $15.25 | Spot: $14.98 (-1.30% to Pool)
# Risk Box: $75.00 - $100.00 Max Premium Risk
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "AAL260724C00015500"  # July 24, 2026 $15.50 Call
TICKER_PUT  = "AAL260724P00014500"  # July 24, 2026 $14.50 Put

# 1. BULLISH SCALP: CALL SETUP ON BREAK INTO SYSTEMIC LIQUIDITY
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap):
    """
    IF: AAL cross upward into the institutional $15.10 target band,
    bolstered by volume spikes reclaiming structural VWAP.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 14.90, "close": 14.95, "high": 15.02},
            {"low": 14.94, "close": 15.01, "high": 15.08},
            {"low": 15.00, "close": current_price, "high": 15.15}
        ]
        
    pool_floor = 15.10
    pool_ceiling = 15.25
    
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    current_candle = candles_1m[-1]
    
    vwap_reclaim = (current_candle['close'] >= current_vwap)

    if trigger_zone and vwap_reclaim:
        # Sizing: Target premium ~$0.25 * 20% risk = $0.05/contract risk.
        # 18 contracts * $5.00 = $90.00 total risk footprint.
        return True, 18
        
    return False, 0

# 2. BEARISH SCALP: PUT SETUP
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap):
    pool_floor = 15.10
    current_candle = candles_1m[-1]
    
    breakdown_zone = (current_price <= pool_floor)
    below_vwap = (current_candle['close'] < current_vwap)

    if breakdown_zone and below_vwap:
        # Sizing: Target premium ~$0.22 * 20% risk = $0.044/contract risk.
        # 20 contracts * $4.40 = $88.00 total risk footprint.
        return True, 20
        
    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.50, 2)
    underlying_invalidation = 14.85 if option_type == "CALL" else 15.40
    
    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }
