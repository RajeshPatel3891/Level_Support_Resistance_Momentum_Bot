cat << 'EOF_CSO_MATRIX' > simulate_cso_matrix.py
import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime

# Absolute pathing relative to this file to guarantee background service safety
current_dir = os.path.dirname(os.path.abspath(__file__))
MACRO_STATE_PATH = os.path.join(current_dir, 'macro_state.json')
TRADING_LEVELS_PATH = os.path.join(current_dir, 'trading_levels.json')

# API Key - Gemini Preview Protocol (The runtime environment automatically injects this)
api_key = ""

def write_macro_state(state):
    """Atomically persists the evaluated macro state to protect against concurrent reads."""
    temp_path = MACRO_STATE_PATH + ".tmp"
    try:
        with open(temp_path, 'w') as f:
            json.dump(state, f, indent=4)
        os.replace(temp_path, MACRO_STATE_PATH)
        return True
    except Exception as e:
        print(f"\033[91m[X] Failed to persist macro state: {e}\033[0m")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False

def extract_json_payload(raw_text):
    """Cleans markdown wrappers if Gemini wraps JSON responses."""
    cleaned = raw_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()

def fetch_latest_sentiment_with_gemini():
    """
    Leverages Gemini-2.5-Flash with Search Grounding to crawl and assess
    real-time global macroeconomic sentiment and geopolitical indicators.
    Includes robust exponential backoff as required by platform specifications.
    """
    global api_key
    active_key = api_key if api_key else os.environ.get("GEMINI_API_KEY", "")
    
    if not active_key:
        print("\033[93m[!] WARNING: GEMINI_API_KEY not found. Using local sandbox fallback engine.\033[0m")
        return get_simulated_crawl_state()

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-09-2025:generateContent?key={active_key}"
    
    system_prompt = (
        "You are the Chief Strategy Officer (CSO) of Harmonized AI. Your job is to crawl global financial "
        "news, analyze real-time market sentiment, index movements, and classify systemic risks. "
        "If there are major shocks (such as heavy pre-holiday liquidation, unexpected labor data misses, "
        "geopolitical escalation, or dramatic rate movements), set risk_bias to 'RISK_OFF_LIQUIDATION' "
        "or 'HIGH_VOLATILITY_SHOCK' and write a detailed operational_directive blocking or curtailing long trades. "
        "Otherwise, maintain risk_bias as 'NEUTRAL' or 'RISK_ON' with 'None'."
    )
    
    payload = {
        "contents": [{
            "parts": [{
                "text": (
                    "Perform a live financial news crawl and macroeconomic sentiment analysis on the US markets "
                    "(focusing on SPY, QQQ index movements, and rate yield catalysts). Determine the current macro regime, "
                    "primary catalyst, risk bias, calendar constraints, and active operational directive."
                )
            }]
        }],
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "macro_regime": {"type": "STRING"},
                    "risk_bias": {"type": "STRING"},
                    "primary_catalyst": {"type": "STRING"},
                    "calendar_constraints": {"type": "STRING"},
                    "operational_directive": {"type": "STRING"}
                },
                "required": ["macro_regime", "risk_bias", "primary_catalyst", "calendar_constraints", "operational_directive"]
            }
        }
    }

    # Exponential Backoff: 1s, 2s, 4s, 8s, 16s
    delays = [1, 2, 4, 8, 16]
    for i, delay in enumerate(delays):
        try:
            response = requests.post(url, json=payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                raw_text = result['candidates'][0]['content']['parts'][0]['text']
                cleaned_text = extract_json_payload(raw_text)
                state = json.loads(cleaned_text)
                state["last_updated"] = datetime.now().isoformat()
                return state
            elif response.status_code in [429, 500, 503]:
                time.sleep(delay)
            else:
                response.raise_for_status()
        except Exception as e:
            if i == len(delays) - 1:
                print(f"\033[93m[!] CSO Live Crawl failed permanently: {e}. Reverting to fallback.\033[0m")
            time.sleep(delay)
            
    return get_simulated_crawl_state()

def get_simulated_crawl_state():
    """Generates a structured high-fidelity mock state for offline testing."""
    return {
        "last_updated": datetime.now().isoformat(),
        "macro_regime": "ACTIVE LIQUIDATION SHOCK / PRE-HOLIDAY DRAIN",
        "primary_catalyst": "BLS Non-Farm Payrolls major miss (+57K vs expectations)",
        "risk_bias": "RISK_OFF_LIQUIDATION",
        "calendar_constraints": "Low liquidity pre-holiday session.",
        "operational_directive": "Enforce maximum defense. Rejects long support tests showing high velocity cascades; volume is likely distribution."
    }

def run_daemon(interval_seconds=900):
    """Background loop that continuously runs the crawler and writes updates."""
    print(f"\033[92m[✓] CSO Background Daemon Mode Engaged.\033[0m")
    print(f"[*] Crawl Loop Interval: {interval_seconds / 60:.1f} minutes.")
    print(f"[*] Writing to: {MACRO_STATE_PATH}")
    print("=" * 60)
    
    try:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{timestamp}] Executing Live news crawl...")
            state = fetch_latest_sentiment_with_gemini()
            if write_macro_state(state):
                print(f"[{timestamp}] Successfully updated macro state. Current Bias: \033[95m{state['risk_bias']}\033[0m")
            else:
                print(f"[{timestamp}] Error persisting state update.")
            
            # Sleep until next crawl window
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("\n\033[93m[!] Daemon Mode terminated by user request.\033[0m")
        sys.exit(0)

def run_interactive_simulation():
    """Reads the latest crawled macro state and prompts the CSO for trade clearance."""
    if not os.path.exists(MACRO_STATE_PATH):
        print("\033[91m[X] Error: macro_state.json not found. Run --daemon first or verify paths.\033[0m")
        return

    with open(MACRO_STATE_PATH, 'r') as f:
        macro_context = json.load(f)

    print("\033[94m")
    print("=" * 70)
    print("🚨 PENDING CSO CLEARANCE AUDIT")
    print("=" * 70)
    print(f"[CRAWLED SENTIMENT] : {macro_context.get('macro_regime')}")
    print(f"[PRIMARY CATALYST]  : {macro_context.get('primary_catalyst')}")
    print(f"[CALENDAR PROFILE]  : {macro_context.get('calendar_constraints')}")
    print(f"[LAST CRAWL TIME]   : {macro_context.get('last_updated')}")
    print("-" * 70)
    print(f"[TECHNICAL SENTRY]  : SPY LONG PROXIMITY TEST AT $740.63")
    print(f"• Sentry Status     : High-Volume Support Hold (2.21x RVOL)")
    print("-" * 70)
    
    is_risk_off = macro_context.get("risk_bias") == "RISK_OFF_LIQUIDATION"
    if is_risk_off:
        print("\033[91m*** FRAMEWORK CONFLICT DETECTED: MACRO SENTINEL OVERRULES TECHNICAL ***\033[0m")
        print(f"Operational Directive: {macro_context.get('operational_directive')}")
        print("\033[93mAction Plan: Order has been intercepted. Recommended to reject 'R'.\033[0m")
    else:
        print("\033[92m*** SENTIMENT OPTIMIZED: Technical alignments match current macro regime. ***\033[0m")
    print("\033[0m" + "=" * 70)

    try:
        choice = input("\nEnter CSO Ruling Code (A = Approve / R = Reject / S = Route to Shadow): ").strip().upper()
    except KeyboardInterrupt:
        print("\n\n[X] Interrupted. Capital Preservation Preserved.")
        sys.exit(0)

    if choice == 'R':
        print("\n\033[91m[✓] RULING RECORDED: Trade Rejected. Capital Preserved.\033[0m\n")
    elif choice == 'S':
        print("\n\033[94m[✓] RULING RECORDED: Routed to Shadow Account. Running simulation log.\033[0m\n")
    elif choice == 'A':
        print("\n\033[91m[!] WARNING: Manual override accepted. Relaying execution sequence...\033[0m\n")
    else:
        print("\n\033[95m[X] INVALID CODE: Order discarded safely.\033[0m\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Harmonized AI CSO Sentinel Service Console")
    parser.add_argument("--daemon", action="store_true", help="Launch continuous background crawl daemon mode")
    parser.add_argument("--interval", type=int, default=900, help="News crawl loop interval in seconds (default: 900s)")
    args = parser.parse_args()

    if args.daemon:
        run_daemon(interval_seconds=args.interval)
    else:
        run_interactive_simulation()
EOF_CSO_MATRIX
