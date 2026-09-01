import math
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from src.GexReader import get_latest_gex_context

# --- ENVIRONMENT RISK CONFIGURATION ---
try:
    OPTION_STOP_LOSS_PCT = float(os.getenv("OPTION_STOP_LOSS_PCT", "0.12"))
except (ValueError, TypeError):
    OPTION_STOP_LOSS_PCT = 0.12

def calculate_gex_hit_probability(spot: float, target: float, gex_label: str = 'POSITIVE', default_daily_vol_pct: float = 0.015) -> float:
    """Calculates win probability using standard deviation Gaussian decay."""
    if spot <= 0 or target <= 0:
        return 50.0

    gap_pct = abs(spot - target) / spot
    z_score = gap_pct / default_daily_vol_pct
    raw_prob = (1.0 - math.erf(z_score / math.sqrt(2))) * 100.0

    regime_boost = 1.15 if 'POSITIVE' in str(gex_label).upper() else 0.85
    final_prob = min(max(raw_prob * regime_boost, 5.0), 95.0)
    return round(final_prob, 1)

def calculate_risk_return_dollars(spot: float, target: float, stop_loss: float, shares: float = 1.0, delta: float = 0.50):
    """Calculates potential TP return and SL risk in dollar amounts."""
    multiplier = delta * 100.0 * shares
    tp_diff = target - spot
    
    # Fallback to configured stop loss percentage if stop loss is undefined
    sl_pct_fallback = float(os.getenv("OPTION_STOP_LOSS_PCT", "0.12"))
    sl_diff = spot - stop_loss if stop_loss > 0 else spot * sl_pct_fallback

    potential_tp_dollar = round(tp_diff * multiplier, 2)
    potential_sl_dollar = round(-abs(sl_diff * multiplier), 2)

    return potential_tp_dollar, potential_sl_dollar

def resolve_direction_targets(ticker: str, last_price: float, direction: str = 'CALL', stored_stop: float = 0.0):
    """Resolves direction-aware GEX target walls and stop losses using environment OPTION_STOP_LOSS_PCT."""
    gex_ctx = get_latest_gex_context(ticker)
    gex_target = None
    gex_label = "NEUTRAL"
    stop_loss_val = float(stored_stop) if stored_stop else 0.0
    
    # Dynamic stop loss multiplier derived from environment (default: 0.12 / 12%)
    sl_pct = float(os.getenv("OPTION_STOP_LOSS_PCT", "0.12"))

    if gex_ctx:
        call_wall = gex_ctx.get('call_wall')
        put_wall = gex_ctx.get('put_wall')
        gamma_flip = gex_ctx.get('gamma_flip')
        gex_label = gex_ctx.get('gex_label', 'NEUTRAL')

        if str(direction).upper() == 'CALL':
            gex_target = call_wall if (call_wall and call_wall > last_price) else (gamma_flip if (gamma_flip and gamma_flip > last_price) else round(last_price * 1.015, 2))
            if stop_loss_val <= 0 or stop_loss_val >= last_price:
                stop_loss_val = put_wall if (put_wall and put_wall < last_price) else round(last_price * (1.0 - sl_pct), 2)
        else:
            gex_target = put_wall if (put_wall and put_wall < last_price) else (gamma_flip if (gamma_flip and gamma_flip < last_price) else round(last_price * (1.0 - sl_pct), 2))
            if stop_loss_val <= 0 or stop_loss_val <= last_price:
                stop_loss_val = call_wall if (call_wall and call_wall > last_price) else round(last_price * (1.0 + sl_pct), 2)

    return gex_target, stop_loss_val, gex_label

def evaluate_cso_informed_exit(spot: float, target: float, stop_loss: float, 
                               prob_win: float, floating_pnl: float, shares: float = 1.0, delta: float = 0.50) -> dict:
    """
    Evaluates Expected Value (EV) and returns CSO exit directives and UI badges.
    """
    p_win = prob_win / 100.0
    p_loss = 1.0 - p_win

    tp_dollar, sl_dollar = calculate_risk_return_dollars(spot, target, stop_loss, shares, delta)
    tp_reward = max(abs(tp_dollar), 0.01)
    sl_risk = max(abs(sl_dollar), 0.01)

    ev_dollars = (p_win * tp_reward) - (p_loss * sl_risk)

    if ev_dollars < 0 and floating_pnl > 0:
        recommendation = "TAKE_PROFIT_NOW"
        reason = f"Negative EV (${ev_dollars:+.2f}) with floating profit (${floating_pnl:+.2f}). Lock gains."
        cso_badge_bg = "bg-emerald-600"
        cso_badge_text = "text-white"
    elif ev_dollars < -2.00:
        recommendation = "TIGHTEN_STOP"
        reason = "Unfavorable expected value path. Tightening stop loss."
        cso_badge_bg = "bg-amber-600"
        cso_badge_text = "text-white"
    else:
        recommendation = "HOLD"
        reason = "Positive or neutral expected value trajectory."
        cso_badge_bg = "bg-gray-800"
        cso_badge_text = "text-gray-300"

    return {
        "ev_dollars": round(ev_dollars, 2),
        "recommendation": recommendation,
        "reason": reason,
        "cso_badge_bg": cso_badge_bg,
        "cso_badge_text": cso_badge_text
    }

import numpy as np
import pandas as pd

def evaluate_orb_vwap_setup(df_1min, orb_minutes=15):
    """
    Evaluates Opening Range Breakout (ORB) paired with VWAP Slope Angle.
    Expects df_1min with columns: ['open', 'high', 'low', 'close', 'volume']
    """
    if df_1min is None or df_1min.empty:
        return {"signal": "NO_DATA", "confidence": 0.0, "reason": "Empty DataFrame"}

    try:
        # Deduplicate columns if Tradier returned duplicate headers
        df = df_1min.loc[:, ~df_1min.columns.duplicated()].copy().reset_index(drop=True)
        
        # Ensure required columns exist and force to 1D float series
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].squeeze(), errors='coerce').astype(float)

        if len(df) < orb_minutes:
            return {"signal": "WAITING", "confidence": 0.0, "reason": f"Awaiting ORB Window ({len(df)}/{orb_minutes} bars)"}

        # 1. Calculate Opening Range (First N minutes)
        orb_df = df.iloc[:orb_minutes]
        orb_high = float(orb_df['high'].max())
        orb_low = float(orb_df['low'].min())

        # 2. Calculate VWAP & VWAP Slope
        typical_price = (df['high'] + df['low'] + df['close']) / 3.0
        pv = typical_price * df['volume']
        
        vwap_series = pv.cumsum() / df['volume'].cumsum()
        df['vwap'] = vwap_series

        current_close = float(df['close'].iloc[-1])
        current_vwap = float(df['vwap'].iloc[-1])

        # VWAP Slope calculation (last 5 periods, flattened to 1D)
        vwap_recent = df['vwap'].iloc[-5:].to_numpy().flatten()
        if len(vwap_recent) < 5 or np.isnan(vwap_recent).any():
            return {"signal": "NO_SETUP", "confidence": 0.0, "reason": "Insufficient VWAP history"}

        x = np.arange(len(vwap_recent), dtype=float)
        slope, _ = np.polyfit(x, vwap_recent, 1)

        # Normalize slope as percentage of price
        normalized_slope = (slope / current_vwap) * 100.0 if current_vwap > 0 else 0.0

        # 3. Trigger Conditions
        if current_close > orb_high and current_close > current_vwap and normalized_slope > 0.12:
            return {
                "signal": "BUY_CALL",
                "confidence": 0.85,
                "reason": f"ORB High Break (${orb_high:.2f}) + VWAP Bullish Slope ({normalized_slope:.3f}%)",
                "orb_high": orb_high,
                "orb_low": orb_low
            }
        elif current_close < orb_low and current_close < current_vwap and normalized_slope < -0.12:
            return {
                "signal": "BUY_PUT",
                "confidence": 0.85,
                "reason": f"ORB Low Break (${orb_low:.2f}) + VWAP Bearish Slope ({normalized_slope:.3f}%)",
                "orb_high": orb_high,
                "orb_low": orb_low
            }

        return {"signal": "NO_SETUP", "confidence": 0.0, "reason": f"Inside ORB (${orb_low:.2f}-${orb_high:.2f}) or Flat VWAP Slope ({normalized_slope:.3f}%)"}
    except Exception as e:
        return {"signal": "ERROR", "confidence": 0.0, "reason": f"ORB Calc Exception: {str(e)}"}

def evaluate_vwap_mean_reversion(df_1min, rsi_period=14):
    """
    Evaluates intraday mean reversion entries back to the VWAP center line
    when GEX Proximity < 50% and price is extended to VWAP 2.0 std dev bands.
    """
    if df_1min is None or df_1min.empty or len(df_1min) < 30:
        return {"signal": "WAITING", "confidence": 0.0, "reason": "Insufficient history for VWAP bands (min 30 bars)"}

    try:
        # Deduplicate columns if Tradier returned duplicate headers
        df = df_1min.loc[:, ~df_1min.columns.duplicated()].copy().reset_index(drop=True)

        # Ensure required columns exist and force to 1D float series
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col].squeeze(), errors='coerce').astype(float)

        # 1. Calculate VWAP and Standard Deviation Bands
        typical_price = (df['high'] + df['low'] + df['close']) / 3.0
        pv = typical_price * df['volume']
        
        cum_vol = df['volume'].cumsum()
        vwap = pv.cumsum() / np.where(cum_vol == 0, 1.0, cum_vol)
        df['vwap'] = vwap

        # Intraday VWAP Standard Deviation
        std_dev = (df['close'] - df['vwap']).expanding().std()
        upper_band = df['vwap'] + (2.0 * std_dev)
        lower_band = df['vwap'] - (2.0 * std_dev)

        current_close = float(df['close'].iloc[-1])
        current_vwap = float(df['vwap'].iloc[-1])
        current_upper = float(upper_band.iloc[-1])
        current_lower = float(lower_band.iloc[-1])

        # 2. Overextended Mean Reversion Signals
        if current_close <= current_lower:
            return {
                "signal": "BUY_CALL",
                "confidence": 0.80,
                "reason": f"Oversold: Spot (${current_close:.2f}) at -2σ VWAP Band (${current_lower:.2f}) -> Targeting Mean (${current_vwap:.2f})",
                "target_price": current_vwap
            }
        elif current_close >= current_upper:
            return {
                "signal": "BUY_PUT",
                "confidence": 0.80,
                "reason": f"Overbought: Spot (${current_close:.2f}) at +2σ VWAP Band (${current_upper:.2f}) -> Targeting Mean (${current_vwap:.2f})",
                "target_price": current_vwap
            }

        return {"signal": "NO_SETUP", "confidence": 0.0, "reason": f"Price (${current_close:.2f}) inside 2σ VWAP bands (${current_lower:.2f}-${current_upper:.2f})"}
    except Exception as e:
        return {"signal": "ERROR", "confidence": 0.0, "reason": f"VWAP Reversion Exception: {str(e)}"}
