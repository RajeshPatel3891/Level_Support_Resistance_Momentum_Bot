# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (AAPL ACCELERATION MATRIX)
# Target Session: Tuesday, July 21, 2026
# Pre-Market Spot: $328.00 | VWAP Anchor: $331.20
# Support Pool: $323.10 - $324.90 | Resistance Pool: $332.10 - $333.90
# Risk Box: $75.00 - $100.00 Max Premium Risk ($85.00 Target)
# ==============================================================================

# --- System & Parameter Initialization (4-DTE Proxy OTM Chain) ---
TICKER_CALL = "AAPL260724C00335000"  # July 24, 2026 $335.00 Call
TICKER_PUT  = "AAPL260724P00320000"  # July 24, 2026 $320.00 Put

PLAYBOOK_CONFIG = {
    "ticker": "AAPL",
    "date": "2026-07-21",
    "spot_anchor": 328.00,
    "vwap_anchor": 331.20,
    "support_zone": [323.10, 324.90],
    "resistance_zone": [332.10, 333.90],
    "risk_per_trade": 85.00,
    "guardrails": {
        "velocity_filter_active": False, # Velocity clean
        "momentum_filter_active": True,  # Require zone hit
        "allow_execution": False        # OUT OF BOUNDS ($328 mid-zone vs $323/$332 zones)
    }
}

# 1. BULLISH SCALP: CALL SETUP ON SUPPORT POOL BOUNCE
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    """
    IF: AAPL pulls back into Support ($323.10 - $324.90) above VWAP ($331.20 or local reclaim),
    and candle closes higher than preceding high.
    """
    if velocity_flag:
        return False, 0

    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 323.00, "close": 323.80, "high": 324.20},
            {"low": 323.50, "close": 324.10, "high": 324.50},
            {"low": 324.00, "close": current_price, "high": current_price + 0.30}
        ]

    pool_floor, pool_ceiling = PLAYBOOK_CONFIG["support_zone"]
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    
    current_candle = candles_1m[-1]
    vwap_reclaim = (current_candle['close'] >= current_vwap)
    momentum_velocity = (current_candle['close'] > candles_1m[-2]['high'])

    if trigger_zone and vwap_reclaim and momentum_velocity:
        # Sizing: Target premium ~$5.20 * 20% risk = $1.04/contract risk.
        # 5 contracts * $104 = $85.00 footprint target.
        return True, 5

    return False, 0

# 2. BEARISH SCALP: PUT SETUP FROM RESISTANCE REJECTION
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    """
    IF: AAPL rallies into Resistance ($332.10 - $333.90) and breaks down below VWAP/prev low.
    """
    if not candles_1m or len(candles_1m) < 3:
        candles_1m = [
            {"low": 331.50, "close": 332.20, "high": 333.00},
            {"low": 332.00, "close": 332.80, "high": 333.50},
            {"low": 331.00, "close": current_price, "high": 333.80}
        ]

    res_floor, res_ceiling = PLAYBOOK_CONFIG["resistance_zone"]
    rejection_zone = (res_floor <= current_price <= res_ceiling)
    current_candle = candles_1m[-1]
    below_vwap_or_rejection = (current_candle['close'] < candles_1m[-2]['low'])

    if rejection_zone and below_vwap_or_rejection:
        return True, 5

    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, option_type):
    stop_loss = round(entry_fill * 0.80, 2)
    tp1_target = round(entry_fill * 1.40, 2)
    underlying_invalidation = 321.50 if option_type == "CALL" else 335.50

    return {
        "stop_loss": stop_loss,
        "tp1": tp1_target,
        "underlying_invalidation": underlying_invalidation
    }

if __name__ == "__main__":
    call_exec, call_qty = evaluate_call_entry([], 328.00, 331.20, velocity_flag=False)
    put_exec, put_qty = evaluate_put_entry([], 328.00, 331.20, velocity_flag=False)
    print("=" * 65)
    print(f"[AAPL Playbook Self-Test] Date: {PLAYBOOK_CONFIG['date']} | Spot: ${PLAYBOOK_CONFIG['spot_anchor']}")
    print(f"[-] Call Triggered : {call_exec} ({call_qty} contracts) | Reason: Out of Bounds ($328 vs $323.10 Support)")
    print(f"[-] Put Triggered  : {put_exec} ({put_qty} contracts) | Reason: Out of Bounds ($328 vs $332.10 Resistance)")
    print("=" * 65)
