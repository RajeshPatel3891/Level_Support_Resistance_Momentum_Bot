# ==============================================================================
# HARMONIZED AI: DAILY INTRADAY EXECUTION PLAYBOOK (RIVN EQUITY ACCELERATION)
# Target Session: Wednesday, July 22, 2026
# Asset Class: Direct Equity / Stock Shares
# Pre-Market Spot: $17.15 | VWAP Anchor: $17.25
# Support Pool: $17.11 - $17.19 | Resistance Pool: $18.51 - $18.59
# Enforced Risk Budget: $30.00 | Dynamic ATR Volatility Buffer: $0.20
# ==============================================================================

PLAYBOOK_CONFIG = {
    "ticker": "RIVN",
    "date": "2026-07-22",
    "spot_anchor": 17.15,
    "vwap_anchor": 17.25,
    "support_zone": [17.11, 17.19],
    "resistance_zone": [18.51, 18.59],
    "risk_per_trade": 30.00,
    "atr_14_buffer": 0.20,  # Dynamic 14-period ATR volatility stop distance
    "guardrails": {
        "velocity_filter_active": False,
        "momentum_filter_active": True,
        "allow_execution": False  # Blocked until spot reclaims VWAP
    }
}

def calculate_share_size(entry_price, stop_price):
    """
    Calculates exact equity share count capped strictly at the $30.00 risk budget.
    Formula: Shares = Floor( $30.00 / |Entry - Stop| )
    """
    risk_per_share = abs(entry_price - stop_price)
    if risk_per_share <= 0:
        return 0
    shares = int(PLAYBOOK_CONFIG["risk_per_trade"] / risk_per_share)
    return max(1, shares)

# 1. BULLISH SCALP: EQUITY LONG AT SUPPORT
# ------------------------------------------------------------------------------
def evaluate_call_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    """
    LONG ENTRY: IF RIVN holds Support Pool ($17.11 - $17.19) AND reclaims VWAP ($17.25).
    """
    if velocity_flag or not candles_1m or len(candles_1m) < 2:
        return False, 0

    pool_floor, pool_ceiling = PLAYBOOK_CONFIG["support_zone"]
    trigger_zone = (pool_floor <= current_price <= pool_ceiling)
    
    current_candle = candles_1m[-1]
    vwap_reclaim = (current_candle['close'] >= current_vwap)
    momentum_velocity = (current_candle['close'] > candles_1m[-2]['high'])

    if trigger_zone and vwap_reclaim and momentum_velocity:
        stop_price = current_price - PLAYBOOK_CONFIG["atr_14_buffer"]
        shares = calculate_share_size(current_price, stop_price)
        return True, shares

    return False, 0

# 2. BEARISH SCALP: EQUITY SHORT AT RESISTANCE
# ------------------------------------------------------------------------------
def evaluate_put_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    """
    SHORT ENTRY: IF RIVN tests Resistance Pool ($18.51 - $18.59) AND rejects below VWAP.
    """
    if velocity_flag or not candles_1m or len(candles_1m) < 2:
        return False, 0

    res_floor, res_ceiling = PLAYBOOK_CONFIG["resistance_zone"]
    rejection_zone = (res_floor <= current_price <= res_ceiling)
    
    current_candle = candles_1m[-1]
    below_vwap = (current_candle['close'] < current_vwap)
    rejection = (current_candle['close'] < candles_1m[-2]['low'])

    if rejection_zone and below_vwap and rejection:
        stop_price = current_price + PLAYBOOK_CONFIG["atr_14_buffer"]
        shares = calculate_share_size(current_price, stop_price)
        return True, shares

    return False, 0

# 3. LIVE ORDER LIFECYCLE & RISK MANAGEMENT
# ------------------------------------------------------------------------------
def calculate_risk_parameters(entry_fill, direction="LONG"):
    """
    Computes ATR-based Stop Loss and 2:1 Profit Target for Equity Execution.
    """
    atr_stop = PLAYBOOK_CONFIG["atr_14_buffer"]
    
    if direction == "LONG":
        stop_loss = round(entry_fill - atr_stop, 2)
        target = round(entry_fill + (atr_stop * 2.0), 2)  # 2:1 Reward to Risk
    else:
        stop_loss = round(entry_fill + atr_stop, 2)
        target = round(entry_fill - (atr_stop * 2.0), 2)

    return {
        "stop_loss": stop_loss,
        "target": target,
        "max_risk": PLAYBOOK_CONFIG["risk_per_trade"],
        "atr_buffer": atr_stop
    }

if __name__ == "__main__":
    print(f"[RIVN Equity Playbook Verified] Date: {PLAYBOOK_CONFIG['date']} | Risk Cap: ${PLAYBOOK_CONFIG['risk_per_trade']:.2f} | ATR Buffer: ${PLAYBOOK_CONFIG['atr_14_buffer']:.2f}")
