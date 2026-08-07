import sqlite3
import json

def can_tactical_force_entry(ticker: str, direction: str, live_quote: dict, atr_val: float) -> tuple[bool, str]:
    """
    Tactical Forced Entry Guard:
    Does NOT affect primary automated logic.
    Only checks if an ARMED position has an acceptable (non-toxic) market structure for a forced fill.
    """
    
    # 1. VERIFY ARMED STATE
    # Ensure we aren't forcing trades on un-analyzed or out-of-bounds tickers
    try:
        with open("trading_levels.json", "r") as f:
            levels = json.load(f)
            ticker_data = levels.get(ticker, {})
            # Check if status is ARMED in manifest
            if ticker_data.get("status") != "ARMED":
                return False, f"REJECTED: {ticker} is not in ARMED state."
    except Exception as e:
        return False, f"REJECTED: Could not verify level manifest state ({e})"

    # 2. SLIPPAGE & SPREAD SANITY CHECK
    # Prevent buying into blown-out ask prices on illiquid options
    bid = float(live_quote.get('bid', 0.0))
    ask = float(live_quote.get('ask', 0.0))
    if ask > 0 and bid > 0:
        spread_pct = (ask - bid) / ask
        if spread_pct > 0.05:  # Block if spread is worse than 5%
            return False, f"REJECTED: Option spread too toxic ({spread_pct:.1%}). Wait for bid/ask to tighten."

    # 3. ATR EXTREME MOMENTUM SPIKE CHECK
    # Ensure we aren't catching a falling knife mid-breakout/breakdown
    spot = float(live_quote.get('last', 0.0))
    high = float(live_quote.get('high', spot))
    low = float(live_quote.get('low', spot))
    current_range = high - low
    
    if atr_val > 0 and current_range > (2.0 * atr_val):
        return False, f"REJECTED: 1-min candle range (${current_range:.2f}) > 2x ATR (${atr_val:.2f}). Extreme momentum against level."

    # 4. PASSED SANITY CHECKS
    return True, f"APPROVED: Tactical forced entry validated for {ticker} ({direction}). Routing order..."
