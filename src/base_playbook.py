import os
import json

# Preflight Guard Interface Contract
PLAYBOOK_CONFIG = {
    "ticker": "BASE",
    "spot_target_call": 100.0,
    "spot_target_put": 90.0,
    "low_nominal_mode": False,
    "min_momentum_score": 0.65
}

def get_dynamic_target(ticker, key, fallback):
    """Dynamically reads real-time calculated levels from trading_levels.json with fallback safety."""
    manifest = "trading_levels.json"
    if os.path.exists(manifest):
        try:
            with open(manifest, "r") as f:
                data = json.load(f)
            val = data.get(ticker, {}).get(key)
            if val is not None and float(val) > 0:
                return float(val)
        except Exception as e:
            print(f"[!] Manifest read exception for {ticker}: {e}")
    return float(fallback)

def evaluate_tradealgo_regime(
    spot: float,
    vwap: float,
    support_zone: list,
    resistance_zone: list,
    rsi_1m: float,
    rvol: float,
    market_alignment: float = 1.0,
    df_bars = None
):
    """
    TradeAlgo 4-Pillar If-Then Decision Engine (Updated Playbook Logic):
    1. Trend Continuation Long (Above VWAP + Bull Flag / Pullback Hold into VWAP/Support)
    2. Mean-Reversion Short / VWAP Fade (Extended 2-3%+ above VWAP into Resistance / Rejection)
    3. Reversal Long at Support (Flush into Higher-Timeframe Support & VWap Reclaim)
    4. Stand-Down Exhaustion / Overextension Filters (>4-5% VWAP deviation or wide spreads/chop)
    """
    if not (spot > 0 and vwap > 0):
        return None, "INVALID_PRICING"

    sup_low, sup_high = (min(support_zone), max(support_zone)) if len(support_zone) >= 2 else (spot * 0.992, spot * 0.998)
    res_low, res_high = (min(resistance_zone), max(resistance_zone)) if len(resistance_zone) >= 2 else (spot * 1.002, spot * 1.008)

    # --------------------------------------------------------------------------
    # RULE D: STAND-DOWN / NO-TRADE FILTERS (Over-extension & Exhaustion)
    # --------------------------------------------------------------------------
    vwap_dev_pct = abs(spot - vwap) / vwap * 100.0
    if spot > vwap and vwap_dev_pct >= 4.0:
        return "STAND_DOWN", f"OVEREXTENDED_HIGH (+{vwap_dev_pct:.1f}% vs VWAP) - NO CHASE / PULLBACK REQUIRED"
    if spot < vwap and vwap_dev_pct >= 4.0:
        return "STAND_DOWN", f"OVEREXTENDED_LOW (-{vwap_dev_pct:.1f}% vs VWAP) - WAIT FOR RECLAIM"

    if rsi_1m > 78.0:
        return "STAND_DOWN", f"RSI_OVERBOUGHT_EXHAUSTION ({rsi_1m:.1f})"
    if rsi_1m < 22.0:
        return "STAND_DOWN", f"RSI_OVERSOLD_EXHAUSTION ({rsi_1m:.1f})"

    # --------------------------------------------------------------------------
    # RULE B: MEAN-REVERSION SHORT / FADE (Spiked 2-3%+ into Known Resistance & Stalled)
    # --------------------------------------------------------------------------
    if spot >= vwap and vwap_dev_pct >= 2.0 and spot >= res_low and rsi_1m >= 68.0:
        return "PUT", f"TRADEALGO_FADE_SHORT (Extended +{vwap_dev_pct:.1f}% into Resistance @ ${res_low:.2f})"

    # --------------------------------------------------------------------------
    # RULE C: REVERSAL LONG AT SUPPORT (Flush into Support + VWAP Reclaim Base)
    # --------------------------------------------------------------------------
    if spot <= sup_high and spot >= sup_low:
        if rvol >= 1.2 and rsi_1m >= 32.0:
            return "CALL", f"TRADEALGO_SUPPORT_REVERSAL_LONG (Flushed to Support Zone [${sup_low:.2f}-${sup_high:.2f}])"

    # --------------------------------------------------------------------------
    # RULE A: TREND CONTINUATION LONG (Above VWAP + Pullback Hold / Bull Flag Pocket)
    # --------------------------------------------------------------------------
    if spot >= vwap and market_alignment >= 0.8:
        in_pullback_pocket = (sup_low <= spot <= (vwap * 1.004)) or (spot >= vwap and (spot - vwap) / vwap <= 0.004)
        if in_pullback_pocket and rvol >= 1.1 and rsi_1m <= 65.0:
            return "CALL", f"TRADEALGO_TREND_LONG (VWAP Hold @ ${vwap:.2f} | Bull Flag Pocket)"

    # --------------------------------------------------------------------------
    # BREAKOUT VS FAKEOUT AT RESISTANCE
    # --------------------------------------------------------------------------
    if spot > res_high and rvol >= 1.8 and spot >= vwap:
        return "CALL", f"TRADEALGO_BREAKOUT_LONG (Cleared Resistance Band @ ${res_high:.2f})"

    if spot < res_low and spot < vwap and rvol >= 1.5 and rsi_1m <= 48.0:
        return "PUT", f"TRADEALGO_FAKEOUT_SHORT (Failed Resistance Reclaim & Lost VWAP)"

    return None, "NO_CONFLUENCE_OR_CHOP"

def evaluate_call_entry(spot_price, vwap, proximity_score, velocity):
    return False, "BASE_TEMPLATE"

def evaluate_put_entry(spot_price, vwap, proximity_score, velocity):
    return False, "BASE_TEMPLATE"
