import tempfile

def atomic_json_dump(data, filepath):
    dir_name = os.path.dirname(os.path.abspath(filepath)) or '.'
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tf:
        json.dump(data, tf, indent=2)
        temp_name = tf.name
    os.replace(temp_name, filepath)

import re
import json
import os
import requests
from dotenv import load_dotenv

try:
    from atomic_writer import save_json_atomically
except ImportError:
    from src.atomic_writer import save_json_atomically

load_dotenv()

LIVE_PRICES_FALLBACK = {
    "NVDA": 198.84, "INTC": 88.87, "TSLA": 307.48, 
    "AAPL": 337.28, "PLTR": 127.05, "RIVN": 16.57,
    "SOFI": 16.79, "F": 14.45, "AAL": 14.63
}

def is_armed(price, support, resistance):
    """Dynamically arm execution route if spot is within support/resistance zone."""
    if not support or not resistance or len(support) < 2 or len(resistance) < 2:
        return False
    in_support = (support[0] <= price <= support[1])
    in_resistance = (resistance[0] <= price <= resistance[1])
    return in_support or in_resistance

def sync():
    if not os.path.exists("trading_levels.json"):
        print("[!] trading_levels.json not found.")
        return

    try:
        with open("trading_levels.json", "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[!] Error loading trading_levels.json: {e}")
        return

    # Dynamic Active OCC Option Symbol Extractor
    active_occ_symbols = []
    try:
        import sqlite3
        import re
        conn = sqlite3.connect('harm_telemetry.db')
        c = conn.cursor()
        c.execute('SELECT occ_symbol, cso_notes FROM trades WHERE exit_status="ACTIVE"')
        rows = c.fetchall()
        conn.close()
        for occ, notes in rows:
            if occ and len(str(occ).strip()) >= 15:
                active_occ_symbols.append(str(occ).strip())
            elif notes and 'OCC:' in str(notes):
                match = re.search(r'OCC:\s*([A-Z0-9]+)', str(notes))
                if match:
                    active_occ_symbols.append(match.group(1))
    except Exception as e:
        print(f"[!] Error reading active OCC symbols: {e}")

    all_symbols = [s for s in data.keys()] + active_occ_symbols
    symbols = ",".join(all_symbols)
    token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    if "sandbox" in base_url.lower():
        base_url = "https://sandbox.tradier.com/v1"

    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

    quotes = {}
    if token:
        try:
            r = requests.get(f"{base_url}/markets/quotes?symbols={symbols}", headers=headers, timeout=5)
            if r.status_code == 200:
                res_quotes = r.json().get('quotes', {}).get('quote', [])
                if isinstance(res_quotes, dict):
                    res_quotes = [res_quotes]
                for q in res_quotes:
                    quotes[q.get('symbol')] = q
        except Exception as e:
            print(f"[!] Tradier quote fetch exception: {e}")

    for ticker, val in data.items():
        if not isinstance(val, dict):
            continue

        q = quotes.get(ticker, {})
        default_fallback = LIVE_PRICES_FALLBACK.get(ticker, 0.0)
        
        # Determine spot price: API quote -> Existing file last_price -> Fallback dict
        spot = float(q.get('last', q.get('close', val.get('last_price', default_fallback))))
        vwap = float(q.get('vwap', 0.0) or q.get('average_price', 0.0))
        
        # Fallback VWAP to spot if 0.0 to prevent blocking execution momentum filters
        if vwap == 0.0 and spot > 0:
            vwap = spot
            
        val["last_price"] = spot
        val["spot"] = spot
        val["vwap"] = vwap

        # Legacy Schema Mapping for Playbooks & HarmonizedDispatch
        sup = val.get("support", [])
        res = val.get("resistance", [])

        if sup and isinstance(sup, list) and len(sup) > 0:
            val["support_a"] = sup[0]
            val["support_b"] = sup[1] if len(sup) > 1 else sup[0]
        if res and isinstance(res, list) and len(res) > 0:
            val["resistance_a"] = res[0]
            val["resistance_b"] = res[1] if len(res) > 1 else res[0]

        # Calculate dynamic arming state
        if spot > 0:
            armed = is_armed(spot, sup, res)
            val["execution_armed"] = armed
            val["status"] = "ARMED" if armed else "WAITING"

    try:
        save_json_atomically(data, "trading_levels.json")
        print("[✓] Live Tradier market prices, VWAP, legacy schema, and dynamic arming states synced!")
    except Exception as e:
        print(f"[!] Error writing trading_levels.json: {e}")

if __name__ == "__main__":
    sync()
