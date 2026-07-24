import math
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

from src.GexReader import get_latest_gex_context

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
    sl_diff = spot - stop_loss if stop_loss > 0 else spot * 0.02

    potential_tp_dollar = round(tp_diff * multiplier, 2)
    potential_sl_dollar = round(-abs(sl_diff * multiplier), 2)

    return potential_tp_dollar, potential_sl_dollar

def resolve_direction_targets(ticker: str, last_price: float, direction: str = 'CALL', stored_stop: float = 0.0):
    """Resolves direction-aware GEX target walls and stop losses."""
    gex_ctx = get_latest_gex_context(ticker)
    gex_target = None
    gex_label = "NEUTRAL"
    stop_loss_val = float(stored_stop) if stored_stop else 0.0

    if gex_ctx:
        call_wall = gex_ctx.get('call_wall')
        put_wall = gex_ctx.get('put_wall')
        gamma_flip = gex_ctx.get('gamma_flip')
        gex_label = gex_ctx.get('gex_label', 'NEUTRAL')

        if str(direction).upper() == 'CALL':
            gex_target = call_wall if (call_wall and call_wall > last_price) else (gamma_flip if (gamma_flip and gamma_flip > last_price) else round(last_price * 1.015, 2))
            if stop_loss_val <= 0 or stop_loss_val >= last_price:
                stop_loss_val = put_wall if (put_wall and put_wall < last_price) else round(last_price * 0.985, 2)
        else:
            gex_target = put_wall if (put_wall and put_wall < last_price) else (gamma_flip if (gamma_flip and gamma_flip < last_price) else round(last_price * 0.985, 2))
            if stop_loss_val <= 0 or stop_loss_val <= last_price:
                stop_loss_val = call_wall if (call_wall and call_wall > last_price) else round(last_price * 1.015, 2)

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
