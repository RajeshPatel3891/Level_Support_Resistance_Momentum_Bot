import json
import requests

# Baseline fallbacks (Used ONLY if live price stream is absent)
FALLBACK_PRICES = {
    "NVDA": 206.85, "INTC": 98.40, "TSLA": 390.00, 
    "AAPL": 328.00, "PLTR": 133.00, "RIVN": 17.15,
    "SOFI": 17.15, "F": 14.15, "AAL": 15.60
}

def is_armed(price, support, resistance):
    """Dynamically arm execution route if spot is within support/resistance zone."""
    if not support or not resistance or len(support) < 2 or len(resistance) < 2:
        return False
    in_support = (support[0] <= price <= support[1])
    in_resistance = (resistance[0] <= price <= resistance[1])
    return in_support or in_resistance

def sync():
    try:
        with open("trading_levels.json", "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[!] Error loading trading_levels.json: {e}")
        return

    for ticker, val in data.items():
        if isinstance(val, dict):
            # Use current dynamic live price if present, otherwise fallback
            price = val.get("last_price")
            if price is None:
                price = FALLBACK_PRICES.get(ticker, 0.0)
                val["last_price"] = price

            sup = val.get("support", [])
            res = val.get("resistance", [])
            
            # Legacy Schema Mapping for Playbooks & HarmonizedDispatch
            if sup and isinstance(sup, list) and len(sup) > 0:
                val["support_a"] = sup[0]
                val["support_b"] = sup[1] if len(sup) > 1 else sup[0]
            if res and isinstance(res, list) and len(res) > 0:
                val["resistance_a"] = res[0]
                val["resistance_b"] = res[1] if len(res) > 1 else res[0]

            # Calculate dynamic arming state
            if price > 0:
                armed = is_armed(price, sup, res)
                val["execution_armed"] = armed
                val["status"] = "ARMED" if armed else "WAITING"

    try:
        with open("trading_levels.json", "w") as f:
            json.dump(data, f, indent=2)
        print("[✓] Market prices preserved and dynamic arming states synced.")
    except Exception as e:
        print(f"[!] Error writing trading_levels.json: {e}")

if __name__ == "__main__":
    sync()
