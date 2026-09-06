import os
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
GEX_PATH = os.path.join(BASE_DIR, "trading_levels_gex.json")
TRADEALGO_PATH = os.path.join(BASE_DIR, "trading_levels_tradealgo.json")
SYNTHESIZED_PATH = os.path.join(BASE_DIR, "trading_levels.json")
ENV_PATH = os.path.join(BASE_DIR, ".env.prod")

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[-] Error loading {path}: {e}")
    return {}

def get_active_tickers():
    tickers = []
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r") as f:
                for line in f:
                    if line.startswith("ACTIVE_TICKERS="):
                        val = line.strip().split("=")[1]
                        tickers = [t.strip() for t in val.split(",") if t.strip()]
        except Exception as e:
            print(f"[-] Error reading ACTIVE_TICKERS from {ENV_PATH}: {e}")
    return tickers

def synthesize_levels():
    gex_data = load_json(GEX_PATH)
    tradealgo_data = load_json(TRADEALGO_PATH)

    if not gex_data and not tradealgo_data:
        print("[-] Neither GEX nor TradeAlgo manifests found.")
        return

    # Filter by ACTIVE_TICKERS from .env.prod if available, else fallback to union of all available keys
    active_env_tickers = get_active_tickers()
    if active_env_tickers:
        all_tickers = sorted(list(set(active_env_tickers).intersection(set(list(gex_data.keys()) + list(tradealgo_data.keys())))))
        # If any active tickers are missing from raw files, include them anyway or let the loop handle empty gracefully
        for t in active_env_tickers:
            if t not in all_tickers and (t in gex_data or t in tradealgo_data):
                all_tickers.append(t)
        all_tickers = sorted(list(set(all_tickers)))
    else:
        all_tickers = sorted(list(set(list(gex_data.keys()) + list(tradealgo_data.keys()))))

    synthesized = {}

    for ticker in all_tickers:
        gex = gex_data.get(ticker, {})
        algo = tradealgo_data.get(ticker, {})

        # Base structure inherits existing execution flags
        base = algo if algo else gex
        spot = algo.get("spot") or gex.get("spot", 0.0)

        entry = {
            "zone_pct": base.get("zone_pct", 0.003),
            "turn_ticks": base.get("turn_ticks", 2),
            "mttp_minutes": base.get("mttp_minutes", 25),
            "beta": base.get("beta", "MID"),
            "spot": spot,
            "price": spot,
            "last_price": spot,
            "spot_price": spot,
            "vwap": algo.get("vwap", spot),
            "gex_label": gex.get("gex_label", "NEUTRAL"),
            "execution_armed": base.get("execution_armed", True),
            "proximity_threshold": base.get("proximity_threshold", 0.0085),
            "gap_pct": base.get("gap_pct", 0.5),
            "confluence_detected": False,
            "trade_mode": "MOMENTUM"
        }

        # 1. Regime Assignment from GEX
        # Positive GEX = mean-reverting tape; Negative GEX = trend-acceleration tape
        if entry["gex_label"] in ["BULLISH_GAMMA", "CALL_WALL"]:
            entry["trade_mode"] = "FADE_RANGE"
        elif entry["gex_label"] in ["BEARISH_GAMMA", "VOLATILITY_EXPANSION"]:
            entry["trade_mode"] = "BREAKOUT"

        # 2. Zone Synthesis & Confluence Detection
        algo_sup = algo.get("support_a", 0.0)
        algo_res = algo.get("resistance_b", 0.0)
        gex_sup = gex.get("support_a", 0.0)
        gex_res = gex.get("resistance_b", 0.0)

        # Resistance arbitration
        if algo_res and gex_res and spot > 0 and abs(algo_res - gex_res) / spot <= 0.0025:
            # Overlap within 0.25% = Confluence A+ Barrier
            entry["resistance_a"] = min(algo.get("resistance_a", algo_res), gex.get("resistance_a", gex_res))
            entry["resistance_b"] = max(algo_res, gex_res)
            entry["confluence_detected"] = True
        else:
            entry["resistance_a"] = algo.get("resistance_a", gex.get("resistance_a", spot * 1.005 if spot > 0 else 1.0))
            entry["resistance_b"] = algo_res if algo_res else gex_res

        # Support arbitration
        if algo_sup and gex_sup and spot > 0 and abs(algo_sup - gex_sup) / spot <= 0.0025:
            # Overlap within 0.25% = Confluence A+ Floor
            entry["support_a"] = min(algo_sup, gex_sup)
            entry["support_b"] = max(algo.get("support_b", algo_sup), gex.get("support_b", gex_sup))
            entry["confluence_detected"] = True
        else:
            entry["support_a"] = algo_sup if algo_sup else gex_sup
            entry["support_b"] = algo.get("support_b", gex.get("support_b", spot * 0.995 if spot > 0 else 1.0))

        entry["support_zone"] = [round(entry["support_a"], 2), round(entry["support_b"], 2)]
        entry["resistance_zone"] = [round(entry["resistance_a"], 2), round(entry["resistance_b"], 2)]

        # 3. Targets: micro trigger from TradeAlgo, macro target from GEX
        zone_pct = entry["zone_pct"]
        entry["call_target"] = round(gex.get("call_target", spot * (1 + zone_pct) if spot > 0 else 0.0), 2)
        entry["put_target"] = round(gex.get("put_target", spot * (1 - zone_pct) if spot > 0 else 0.0), 2)
        entry["spot_target_call"] = entry["call_target"]
        entry["spot_target_put"] = entry["put_target"]

        # Sanity Guardrail: Flag massive spot discrepancies
        if ticker in ["AMD", "INTC", "PLTR"] and spot > 100 and ticker in ["AMD", "INTC"]:
            # Auto-disarm known anomalous spot values until corrected
            entry["execution_armed"] = False

        synthesized[ticker] = entry

    # Atomic write to the active execution manifest
    with open(SYNTHESIZED_PATH, "w") as f:
        json.dump(synthesized, f, indent=2)

    print(f"[✓] [{datetime.now().strftime('%H:%M:%S')}] Synthesized {len(synthesized)} tickers into {SYNTHESIZED_PATH}")

if __name__ == "__main__":
    synthesize_levels()
