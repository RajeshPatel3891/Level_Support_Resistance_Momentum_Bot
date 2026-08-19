import os
import sys
import inspect

# Module path resolution for local imports
sys.path.extend([".", "src", "/app", "/app/src"])

from gemini_cso_live_evaluator import evaluate_cso_decision
import smart_cso_injector

def ai_guided_cso_scout_and_execute(ticker: str, contract_qty: int = 1, market_context: dict = None) -> dict:
    """
    Combines Gemini CSO AI evaluation with Smart CSO execution microstructure.
    """
    print(f"\n[🧠 AI CSO ORCHESTRATOR] Evaluating live setup for {ticker}...")

    # 1. Gather live market context if not provided
    if not market_context:
        if hasattr(smart_cso_injector, 'get_live_market_context'):
            market_context = smart_cso_injector.get_live_market_context(ticker)
        else:
            market_context = {}

    # 2. Invoke Gemini CSO live decision engine
    decision = evaluate_cso_decision(ticker, market_context)
    
    print(f"   ├─ Action      : {decision.action}")
    print(f"   ├─ Confidence  : {decision.confidence * 100:.1f}%")
    print(f"   ├─ Exec Tier   : Tier {decision.suggested_tier}")
    print(f"   └─ CSO Reason  : {decision.reasoning}")

    # 3. Process Action Directive
    if decision.action == "ENTER" and decision.confidence >= 0.70:
        print(f"🚀 [CSO CONFIRMED] High-conviction entry trigger for {ticker}. Executing Order...")
        
        # Dynamically build kwargs supported by smart_cso_scout_and_execute signature
        sig = inspect.signature(smart_cso_injector.smart_cso_scout_and_execute)
        kwargs = {}
        if 'contract_qty' in sig.parameters:
            kwargs['contract_qty'] = contract_qty
        if 'initial_tier' in sig.parameters:
            kwargs['initial_tier'] = decision.suggested_tier

        # Pass ticker positionally to avoid parameter naming mismatches (e.g. ticker vs target_ticker)
        return smart_cso_injector.smart_cso_scout_and_execute(ticker, **kwargs)
    
    elif decision.action == "EXIT":
        print(f"🚨 [CSO EXIT SIGNAL] Triggering immediate position close for {ticker}...")
        if hasattr(smart_cso_injector, 'execute_adaptive_close'):
            return smart_cso_injector.execute_adaptive_close(ticker)
        else:
            print("[!] execute_adaptive_close function not found in smart_cso_injector")
            return {"status": "ERROR", "reason": "Missing execute_adaptive_close"}
        
    else:
        print(f"⏳ [CSO NO-ACTION] Decision is '{decision.action}'. Standing down.")
        return {"status": "HOLD", "reason": decision.reasoning}

if __name__ == '__main__':
    # Dry-run context test for SOFI
    sample_context = {
        "spot": 18.33,
        "target": 18.33,
        "dist_pct": 0.00,
        "option_symbol": "SOFI260821C00018500",
        "bid": 0.35, "ask": 0.37, "spread": 0.02,
        "tick_stream": [18.34, 18.32, 18.33],
        "position_state": "FLAT"
    }
    print("[*] Running dry-run test for SOFI...")
    res = ai_guided_cso_scout_and_execute("SOFI", contract_qty=1, market_context=sample_context)
    print("\n[✓] Orchestrator Output:", res)
