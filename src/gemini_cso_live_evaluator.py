#!/usr/bin/env python3
"""
HARM.AI // LIVE GEMINI CSO ENTRY & EXIT DECISION ENGINE (WITH 503 FAILOVER)
===============================================================================
Passes real-time tick context to Gemini to evaluate:
1. ENTRY DECISION: Should we inject a trade based on GEX zone & micro-velocity?
2. EXIT DECISION: Should we hold, take profit, or trigger MTTP exit?

Failover Architecture:
gemini-3.5-flash -> gemini-3.1-flash-lite -> gemini-3.6-flash -> Rule-Based Fallback
"""

import os
import sys
import json
import time
from datetime import datetime
from pydantic import BaseModel, Field
from dotenv import load_dotenv

if os.path.exists(".env.prod"):
    load_dotenv(".env.prod", override=True)
else:
    load_dotenv(override=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

class CSODecisionSchema(BaseModel):
    action: str = Field(description="Action to take: 'ENTER', 'HOLD', or 'EXIT'")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0")
    suggested_tier: int = Field(description="Suggested execution tier: 1 (Inside Bid), 2 (Midpoint), or 3 (Sub-Ask)")
    reasoning: str = Field(description="Concise strategic explanation for the decision")

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [LIVE_CSO_EVAL] {msg}")

def evaluate_cso_decision(ticker: str, market_context: dict) -> CSODecisionSchema:
    """Invokes Gemini CSO with automatic secondary model failover on 503 spikes."""
    prompt = f"""
    You are the Chief Strategy Officer (CSO) for HARM.AI automated trading.
    Evaluate the following real-time market context for ticker '{ticker}':

    - Spot Price: ${market_context.get('spot', 0.0):.2f}
    - GEX Target Level: ${market_context.get('target', 0.0):.2f}
    - Zone Distance: {market_context.get('dist_pct', 0.0):.2f}%
    - Option Contract: {market_context.get('option_symbol', 'N/A')}
    - Bid / Ask: ${market_context.get('bid', 0.0):.2f} / ${market_context.get('ask', 0.0):.2f} (Spread: ${market_context.get('spread', 0.0):.2f})
    - Recent Tick Stream: {market_context.get('tick_stream', [])}
    - Current Position State: {market_context.get('position_state', 'FLAT')}

    Make a high-conviction decision:
    - If FLAT and tick velocity indicates a clean bottom bounce inside zone -> action: 'ENTER'
    - If IN POSITION and target hit or time limit reached -> action: 'EXIT'
    - Otherwise -> action: 'HOLD'
    """

    model_priority_chain = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.6-flash"]

    try:
        from google import genai
        client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else genai.Client()

        for model_id in model_priority_chain:
            try:
                response = client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config={
                        'response_mime_type': 'application/json',
                        'response_schema': CSODecisionSchema
                    }
                )
                result_dict = json.loads(response.text)
                return CSODecisionSchema(**result_dict)
            except Exception as inner_e:
                if "503" in str(inner_e) or "UNAVAILABLE" in str(inner_e):
                    log_msg(f"[!] {model_id} hit 503 capacity spike. Failing over to next model...")
                    continue
                else:
                    raise inner_e

    except Exception as e:
        log_msg(f"[!] All AI model routes unavailable: {e}")

    # Deterministic Rule-Based Fallback
    return CSODecisionSchema(
        action="ENTER" if market_context.get("dist_pct", 1.0) <= 0.3 and market_context.get("position_state") == "FLAT" else ("EXIT" if "ACTIVE" in market_context.get("position_state", "") else "HOLD"),
        confidence=0.75,
        suggested_tier=1 if market_context.get("spread", 0.1) <= 0.02 else 2,
        reasoning="Rule-based fallback active."
    )

def run_live_decision_demo():
    print("=" * 80)
    print("🦅 HARM.AI // GEMINI CSO REAL-TIME ENTRY & EXIT INSPECTOR")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} EST\n")

    # TEST SCENARIO A: SOFI Entry Bounce Setup
    sofi_context = {
        "spot": 18.33,
        "target": 18.33,
        "dist_pct": 0.00,
        "option_symbol": "SOFI260821C00018500",
        "bid": 0.35, "ask": 0.37, "spread": 0.02,
        "tick_stream": [18.34, 18.32, 18.33],
        "position_state": "FLAT"
    }

    log_msg("Sending Market Scenario A (SOFI Entry Bounce) to Gemini CSO...")
    dec_a = evaluate_cso_decision("SOFI", sofi_context)
    print(f"  ├─ ACTION:         [{dec_a.action}]")
    print(f"  ├─ CONFIDENCE:     {dec_a.confidence * 100:.1f}%")
    print(f"  ├─ EXEC TIER:      Tier {dec_a.suggested_tier}")
    print(f"  └─ CSO REASONING:  {dec_a.reasoning}\n")

    # TEST SCENARIO B: NVDA Position Take-Profit Exit Setup
    nvda_context = {
        "spot": 226.50,
        "target": 226.43,
        "dist_pct": 0.03,
        "option_symbol": "NVDA260821C00225000",
        "bid": 2.70, "ask": 2.75, "spread": 0.05,
        "tick_stream": [226.10, 226.35, 226.50],
        "position_state": "ACTIVE (Purchased @ $1.80 | UnRealized PnL: +50.0%)"
    }

    log_msg("Sending Market Scenario B (NVDA +50% TP Exit) to Gemini CSO...")
    dec_b = evaluate_cso_decision("NVDA", nvda_context)
    print(f"  ├─ ACTION:         [{dec_b.action}]")
    print(f"  ├─ CONFIDENCE:     {dec_b.confidence * 100:.1f}%")
    print(f"  ├─ EXEC TIER:      Tier {dec_b.suggested_tier}")
    print(f"  └─ CSO REASONING:  {dec_b.reasoning}\n")

    print("=" * 80)

if __name__ == "__main__":
    run_live_decision_demo()
