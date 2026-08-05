#!/usr/bin/env python3
import os
import json
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [CSO_ENGINE] - %(levelname)s - %(message)s")

def evaluate_macro_rebound(trade_telemetry: dict) -> dict:
    """
    Acts as Chief Strategy Officer (CSO) to evaluate whether a position hit by -20% soft stop
    is experiencing a structural macro breakdown (CUT) or normal GEX noise (HOLD),
    incorporating time-in-trade decay, Tradier option greeks (Theta/Delta ratio), 
    and small-cap weekly expiration cutoff rules.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    
    ticker = trade_telemetry.get("ticker", "UNKNOWN")
    drawdown_pct = trade_telemetry.get("drawdown_pct", 0.0)
    time_in_trade = trade_telemetry.get("time_in_trade_minutes", 0.0)
    mttp_limit = trade_telemetry.get("mttp_max_limit", 45)
    
    # Extract Tradier options decay metrics
    theta = trade_telemetry.get("theta", 0.0)
    delta = trade_telemetry.get("delta", 0.50)
    theta_delta_ratio = trade_telemetry.get("theta_delta_ratio", 0.0)
    is_weekly = trade_telemetry.get("is_weekly_0dte", False)
    decay_warning = trade_telemetry.get("decay_warning", "NORMAL")

    # Decay-aware fallback decision when API key is missing or request fails
    if not api_key:
        logging.warning("GEMINI_API_KEY not found in environment.")
        if decay_warning == "CRITICAL_THETA_BLEED" or time_in_trade > 30.0 or theta_delta_ratio > 0.30:
            return {
                "verdict": "CUT_EARLY", 
                "confidence": 0.85, 
                "reasoning": f"Fallback Rule: High theta decay ({time_in_trade}m in trade, ratio {theta_delta_ratio}). Cutting early to preserve capital."
            }
        return {
            "verdict": "HOLD_REBOUND", 
            "confidence": 0.50, 
            "reasoning": "Fallback Rule: Missing API Key. Low decay metrics, holding for rebound."
        }

    client = genai.Client(api_key=api_key)

    system_instruction = f"""
    You are the Chief Strategy Officer (CSO) and Lead Risk Strategist for an automated options trading desk.
    Your sole task is to analyze intraday trade telemetry when an option position hits a -20% drawdown soft-stop.

    You must decide between two actions:
    1. "CUT_EARLY": The position exhibits a structural macro breakdown, severe theta decay, or irreversible options delta collapse. Cut now to preserve capital.
    2. "HOLD_REBOUND": The underlying stock drop is isolated GEX level noise, oversold on high-volume support, or supported by strong broad-market indices. Allow position to seek ATR rebound up to the hard cap.

    EXECUTIVE EVALUATION & THETA DECAY RULES:
    1. TIME DECAY AWARENESS:
       - Elapsed Time: {time_in_trade} minutes out of max {mttp_limit} minutes.
       - If time_in_trade > 30 minutes AND contract is a weekly/0DTE option:
         Aggressively favor "CUT_EARLY". Options theta decay accelerates exponentially in final minutes;
         even if the underlying stock bounces slightly, option premium recovery is unlikely.

    2. OPTION GREEKS & THETA/DELTA RATIO:
       - Live Theta (Θ): {theta} | Live Delta (Δ): {delta}
       - Theta-to-Delta Ratio: {theta_delta_ratio}
       - Decay Warning Status: {decay_warning}
       - If theta_delta_ratio > 0.30 (Theta bleeding faster than Delta can recover), default to "CUT_EARLY".

    3. SMALL-CAP WEEKLY CUTOFF RULE:
       - For small-cap/weekly tickers (e.g. SOFI, RIVN, F, INTC) in drawdown:
         If time_in_trade > 25 minutes AND drawdown < -15%, DO NOT wait for support bounce.
         Advise "CUT_EARLY" to preserve remaining capital.

    OUTPUT REQUIREMENT:
    Return strictly valid JSON matching this schema:
    {{
      "verdict": "CUT_EARLY" | "HOLD_REBOUND",
      "confidence": float (0.0 to 1.0),
      "reasoning": "Short 1-2 sentence technical & decay rationale"
    }}
    """

    prompt = f"""
    Evaluate this active position escalation:
    - Ticker: {ticker}
    - Time-in-Trade: {time_in_trade}m / {mttp_limit}m max (Weekly/0DTE: {is_weekly})
    - Option Entry Premium: ${trade_telemetry.get('entry_premium', 0.0):.2f}
    - Current Option Premium: ${trade_telemetry.get('current_premium', 0.0):.2f} (Drawdown: {drawdown_pct:.1f}%)
    - Option Greeks: Theta={theta:.3f} | Delta={delta:.3f} | Θ/Δ Ratio={theta_delta_ratio:.2f} (Warning: {decay_warning})
    - Underlying Spot Price: ${trade_telemetry.get('spot_price', 0.0):.2f}
    - Underlying VWAP: ${trade_telemetry.get('vwap', 0.0):.2f}
    - Active Support Level: {trade_telemetry.get('support_zone', 'N/A')}
    - Active Resistance Level: {trade_telemetry.get('resistance_zone', 'N/A')}
    - Market Context (QQQ/SPY Trend): {trade_telemetry.get('market_trend', 'NEUTRAL')}
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                temperature=0.2
            )
        )
        
        result = json.loads(response.text)
        logging.info(f"CSO Verdict for {ticker}: {result.get('verdict')} (Confidence: {result.get('confidence')})")
        return result

    except Exception as e:
        logging.error(f"Failed to execute CSO Gemini evaluation: {e}")
        if decay_warning == "CRITICAL_THETA_BLEED" or time_in_trade > 30.0 or theta_delta_ratio > 0.30:
            return {"verdict": "CUT_EARLY", "confidence": 0.80, "reasoning": f"API Exception Fallback: Critical theta decay detected ({time_in_trade}m in trade). Cutting early."}
        return {"verdict": "HOLD_REBOUND", "confidence": 0.50, "reasoning": f"CSO API Execution Error: {str(e)}"}

if __name__ == "__main__":
    test_data = {
        "ticker": "TSLA",
        "time_in_trade_minutes": 10.0,
        "mttp_max_limit": 45,
        "entry_premium": 2.50,
        "current_premium": 2.00,
        "drawdown_pct": -20.0,
        "spot_price": 388.50,
        "vwap": 390.10,
        "theta": -0.05,
        "delta": 0.50,
        "theta_delta_ratio": 0.10,
        "is_weekly_0dte": False,
        "decay_warning": "NORMAL",
        "support_zone": "[384.10 - 385.90]",
        "resistance_zone": "[400.10 - 401.90]",
        "market_trend": "QQQ +0.45% Bullish, SPY VWAP Holding"
    }
    print("Testing CSO Evaluator with mock payload...")
    res = evaluate_macro_rebound(test_data)
    print(json.dumps(res, indent=2))
