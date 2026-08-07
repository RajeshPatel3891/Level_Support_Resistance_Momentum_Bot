#!/usr/bin/env python3
import os
import json
import logging
from google import genai
from google.genai import types

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - [CSO_ENGINE] - %(levelname)s - %(message)s")

def evaluate_macro_rebound(trade_telemetry: dict) -> dict:
    """
    Acts as Chief Strategy Officer (CSO) to evaluate whether a position hit by -20% soft stop
    is experiencing a structural macro breakdown (CUT) or normal GEX noise (HOLD).
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logging.warning("GEMINI_API_KEY not found in environment. Defaulting to HOLD_REBOUND for safety.")
        return {"verdict": "HOLD_REBOUND", "confidence": 0.50, "reasoning": "Missing Gemini API key in environment."}

    client = genai.Client(api_key=api_key)

    system_instruction = """
    You are the Chief Strategy Officer (CSO) and Lead Risk Strategist for an automated options trading desk.
    Your sole task is to analyze intraday trade telemetry when an option position hits a -20% drawdown soft-stop.
    
    You must decide between two actions:
    1. "CUT_EARLY": The underlying stock exhibits a structural macro breakdown, sector divergence, or severe tape velocity drop. Cut now to preserve 80% of contract capital.
    2. "HOLD_REBOUND": The underlying stock drop is isolated GEX level noise, oversold on high-volume support, or supported by strong broad-market indices (QQQ/SPY). Allow position to seek ATR rebound up to the hard cap.

    OUTPUT REQUIREMENT:
    Return strictly valid JSON matching this schema:
    {
      "verdict": "CUT_EARLY" | "HOLD_REBOUND",
      "confidence": float (0.0 to 1.0),
      "reasoning": "Short 1-2 sentence tactical justification"
    }
    """

    prompt = f"""
    Evaluate this active position escalation:
    - Ticker: {trade_telemetry.get('ticker')}
    - Option Entry Premium: ${trade_telemetry.get('entry_premium', 0.0):.2f}
    - Current Option Premium: ${trade_telemetry.get('current_premium', 0.0):.2f} (Drawdown: {trade_telemetry.get('drawdown_pct', 0.0):.1f}%)
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
        logging.info(f"CSO Verdict for {trade_telemetry.get('ticker')}: {result.get('verdict')} (Confidence: {result.get('confidence')})")
        return result

    except Exception as e:
        logging.error(f"Failed to execute CSO Gemini evaluation: {e}")
        return {"verdict": "HOLD_REBOUND", "confidence": 0.50, "reasoning": f"CSO API Execution Error: {str(e)}"}

if __name__ == "__main__":
    # Test Payload
    test_data = {
        "ticker": "TSLA",
        "entry_premium": 2.50,
        "current_premium": 2.00,
        "drawdown_pct": -20.0,
        "spot_price": 388.50,
        "vwap": 390.10,
        "support_zone": "[384.10 - 385.90]",
        "resistance_zone": "[400.10 - 401.90]",
        "market_trend": "QQQ +0.45% Bullish, SPY VWAP Holding"
    }
    print("Testing CSO Evaluator with mock payload...")
    res = evaluate_macro_rebound(test_data)
    print(json.dumps(res, indent=2))
