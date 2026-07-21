# Target Session: Tuesday, July 21, 2026
TICKER_CALL = "INTC260724C00100000"
TICKER_PUT  = "INTC260724P00095000"

PLAYBOOK_CONFIG = {
    "ticker": "INTC", "date": "2026-07-21", "spot_anchor": 97.06, "vwap_anchor": 98.20,
    "support_zone": [96.10, 97.50], "resistance_zone": [100.10, 101.50], "risk_per_trade": 85.00
}

def evaluate_call_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    if velocity_flag: return False, 0
    if not candles_1m: candles_1m = [{"low": 96.50, "close": current_price, "high": current_price + 0.30}]
    trigger_zone = (96.10 <= current_price <= 97.50)
    vwap_reclaim = (candles_1m[-1]['close'] >= current_vwap)
    return (trigger_zone and vwap_reclaim), 6

def evaluate_put_entry(candles_1m, current_price, current_vwap, velocity_flag=False):
    if not candles_1m: candles_1m = [{"low": 99.50, "close": current_price, "high": 101.80}]
    rejection_zone = (100.10 <= current_price <= 101.50)
    below_vwap = (candles_1m[-1]['close'] < current_vwap)
    return (rejection_zone and below_vwap), 6

def calculate_risk_parameters(entry_fill, option_type):
    return {"stop_loss": round(entry_fill * 0.80, 2), "tp1": round(entry_fill * 1.40, 2), "underlying_invalidation": 95.50 if option_type == "CALL" else 102.50}
