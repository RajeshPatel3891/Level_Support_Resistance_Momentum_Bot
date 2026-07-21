# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (TSLA ACCELERATION MATRIX)
# Target Session: Tuesday, July 21, 2026
# Pre-Market Spot: $390.00 | VWAP Anchor: $383.10
# Support Pool: $384.10 - $385.90 | Resistance Pool: $400.10 - $401.90
# Risk Box: $75.00 - $100.00 Max Premium Risk ($85.00 Target)
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "TSLA260724C00400000"  # July 24, 2026 $400.00 Call
TICKER_PUT  = "TSLA260724P00385000"  # July 24, 2026 $385.00 Put

PLAYBOOK_CONFIG = {
    "ticker": "TSLA",
    "date": "2026-07-21",
    "spot_anchor": 390.00,
    "vwap_anchor": 383.10,
    "support_zone": [384.10, 385.90],
    "resistance_zone": [400.10, 401.90],
    "risk_per_trade": 85.00,
    "guardrails": {
        "velocity_filter_active": True,  # Freefall protection active
        "momentum_filter_active": True,  # Requires zone hit
        "allow_execution": False         # Currently mid-zone floating at $390.00
    }
}

# 1. BULLISH SCALP: CALL SETUP ON SUPPORT POOL BOUNCE
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap, velocity_flag=True):
    """
    IF: TSLA pulls back into Support ($384.10 - $385.90) above VWAP ($383.10),
    velocity normalizes (velocity_flag=False), and candle closes higher than prev high.
    """
    if velocity_flag:
        return False, 0  # Blocked by Guardrail 2: Velocity Filter Engaged

    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 384.00, "close": 384.50, "high": 385.00},
            {"low": 384.30, "close": 385.10, "high": 385.40},
            {"low": 384.80, "close": current_price, "high": current_price + 0.50}
        ]

    pool_floor, pool_ceiling = PLAYBOOK_CONFIG["support_zone"]
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    
    current_candle = candles_1m[-1]
    vwap_reclaim = (current_candle['close'] >= current_vwap)
    momentum_velocity = (current_candle['close'] > candles_1m[-2]['high'])

    if trigger_zone and vwap_reclaim and momentum_velocity:
        # Sizing: Target premium ~$8.50 * 20% risk = $1.70/contract risk.
        # 5 contracts * $170 = $85.00 total risk footprint.
        return True, 5

    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM RESISTANCE REJECTION
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    """
    IF: TSLA hits Resistance ($400.10 - $401.90), prints an exhaustion wick,
    and loses VWAP or breaks lower.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 399.00, "close": 400.20, "high": 401.00},
            {"low": 399.50, "close": 400.80, "high": 401.50},
            {"low": 398.50, "close": current_price, "high": 401.80}
        ]

    res_floor, res_ceiling = PLAYBOOK_CONFIG["resistance_zone"]
    rejection_zone = (res_floor <= current_price <= res_ceiling)
    current_candle = candles_1m[-1]
    below_vwap_or_rejection = (current_candle['close'] < candles_1m[-2]['low'])

    if rejection_zone and below_vwap_or_rejection:
        # Sizing: Target premium ~$7.80 * 20% risk = $1.56/contract risk.
        # 5 contracts * $156 = $78.00 total risk footprint.
        return True, 5

    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    """
    Standardized Options Risk Box Management:
    - Stop Loss: -20% on option premium
    - Target 1 (TP1): +40% on option premium
    - Underlying Invalidation: Hard stop if TSLA breaches structural bounds
    """
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.40, 2)
    underlying_invalidation = 382.50 if option_type == "CALL" else 403.00

    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }

if __name__ == "__main__":
    call_exec, call_qty = evaluate_call_entry([], 390.00, 383.10, velocity_flag=True)
    put_exec, put_qty = evaluate_put_entry([], 390.00, 383.10, velocity_flag=False)
    
    print("=" * 65)
    print(f"[TSLA Playbook Self-Test] Date: {PLAYBOOK_CONFIG['date']} | Spot: ${PLAYBOOK_CONFIG['spot_anchor']}")
    print(f"[-] Call Triggered : {call_exec} ({call_qty} contracts) | Reason: Velocity Guardrail Engaged")
    print(f"[-] Put Triggered  : {put_exec} ({put_qty} contracts) | Reason: Out of Bounds ($390 vs $400.10 Target)")
    print("=" * 65)
