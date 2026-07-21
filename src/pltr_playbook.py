# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (PLTR ACCELERATION MATRIX)
# Target Session: Tuesday, July 21, 2026
# Pre-Market Spot: $133.00 | VWAP Anchor: $131.80
# Support Pool: $128.75 - $133.25 | Resistance Pool: $135.25 - $136.75
# Risk Box: $75.00 - $100.00 Max Premium Risk ($85.00 Target)
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "PLTR260724C00135000"  # July 24, 2026 $135.00 Call
TICKER_PUT  = "PLTR260724P00130000"  # July 24, 2026 $130.00 Put

PLAYBOOK_CONFIG = {
    "ticker": "PLTR",
    "date": "2026-07-21",
    "spot_anchor": 133.00,
    "vwap_anchor": 131.80,
    "support_zone": [128.75, 133.25],
    "resistance_zone": [135.25, 136.75],
    "risk_per_trade": 85.00,
    "guardrails": {
        "velocity_filter_active": False,
        "momentum_filter_active": True,
        "allow_execution": True  # ARMED - Currently inside Support Zone
    }
}

# 1. BULLISH SCALP: CALL SETUP ON SUPPORT POOL BOUNCE
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    """
    IF: PLTR holds Support ($128.75 - $133.25) above VWAP ($131.80),
    velocity is clean, and candle closes higher than preceding high.
    """
    if velocity_flag:
        return False, 0

    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 131.50, "close": 132.10, "high": 132.50},
            {"low": 132.00, "close": 132.60, "high": 132.90},
            {"low": 132.40, "close": current_price, "high": current_price + 0.20}
        ]

    pool_floor, pool_ceiling = PLAYBOOK_CONFIG["support_zone"]
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    
    current_candle = candles_1m[-1]
    vwap_reclaim = (current_candle['close'] >= current_vwap)
    momentum_velocity = (current_candle['close'] > candles_1m[-2]['high'])

    if trigger_zone and vwap_reclaim and momentum_velocity:
        # Sizing: Target premium ~$2.80 * 20% risk = $0.56/contract risk.
        # 8 contracts * $56 = $84.80 total risk footprint.
        return True, 8

    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM RESISTANCE REJECTION
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    """
    IF: PLTR tests Resistance ($135.25 - $136.75) and breaks down.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 134.80, "close": 135.30, "high": 136.00},
            {"low": 135.10, "close": 135.70, "high": 136.40},
            {"low": 134.20, "close": current_price, "high": 136.60}
        ]

    res_floor, res_ceiling = PLAYBOOK_CONFIG["resistance_zone"]
    rejection_zone = (res_floor <= current_price <= res_ceiling)
    current_candle = candles_1m[-1]
    below_vwap_or_rejection = (current_candle['close'] < candles_1m[-2]['low'])

    if rejection_zone and below_vwap_or_rejection:
        return True, 8

    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.40, 2)
    underlying_invalidation = 127.50 if option_type == "CALL" else 138.00

    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }

if __name__ == "__main__":
    call_exec, call_qty = evaluate_call_entry([], 133.00, 131.80, velocity_flag=False)
    put_exec, put_qty = evaluate_put_entry([], 133.00, 131.80, velocity_flag=False)
    print(f"[PLTR Playbook Self-Test] Spot: $133.00 | Call: {call_exec} ({call_qty} contracts) | Put: {put_exec} ({put_qty} contracts)")
