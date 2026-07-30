import sqlite3
import json
import time
import subprocess
import os
import urllib.request
import urllib.parse
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

DB_PATH = "harm_telemetry.db"
LEVELS_PATH = "trading_levels.json"

TRADIER_TOKEN = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
TRADIER_BASE = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")

def format_occ_symbol(ticker, direction, spot_price):
    """
    Constructs a standard 21-character OCC option symbol string.
    Example: TSLA260730C00308000
    """
    opt_type = 'C' if str(direction).upper() == 'CALL' else 'P'
    exp_date = "260730"  # 2026-07-30
    
    # Strike formatted as 8 digits (scaled by 1000)
    strike_val = int(round(spot_price) * 1000)
    root = f"{ticker[:6]:<6}".replace(" ", "")
    
    return f"{root}{exp_date}{opt_type}{strike_val:08d}"

def fetch_live_tradier_option(ticker, direction, spot_price):
    """
    Fetches the actual near-the-money 0DTE OCC contract symbol and live Ask price
    directly from Tradier API with safe dictionary parsing.
    """
    if not TRADIER_TOKEN:
        print("[!] Warning: Tradier token missing from environment.")
        return fallback_option_calc(ticker, direction, spot_price)

    try:
        exp_date = "2026-07-30"
        url = f"{TRADIER_BASE}/markets/options/chains?symbol={ticker}&expiration={exp_date}&greeks=false"
        
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {TRADIER_TOKEN}",
                "Accept": "application/json"
            }
        )
        
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                raw_body = resp.read().decode()
                data = json.loads(raw_body) if raw_body else {}
                
                if isinstance(data, dict) and data.get("options"):
                    options_obj = data["options"]
                    if isinstance(options_obj, dict):
                        options = options_obj.get("option", [])
                        if isinstance(options, dict):
                            options = [options]
                        
                        opt_type = direction.lower()
                        matching = [o for o in options if isinstance(o, dict) and o.get("option_type") == opt_type]
                        
                        if matching:
                            closest = min(matching, key=lambda x: abs(float(x.get("strike", 0)) - spot_price))
                            occ = closest.get("symbol")
                            ask = float(closest.get("ask") or closest.get("last") or 0.50)
                            if occ and len(occ) >= 15:
                                print(f"[✓] Tradier Market Direct -> {ticker} Strike: ${closest.get('strike')} | Ask: ${ask} | OCC: {occ}")
                                return ask, occ
    except Exception as e:
        print(f"[-] Tradier Option API lookup exception for {ticker}: {e}")

    return fallback_option_calc(ticker, direction, spot_price)

def fallback_option_calc(ticker, direction, spot_price):
    est_cost = round(max(spot_price * 0.035, 0.35), 2)
    occ = format_occ_symbol(ticker, direction, spot_price)
    return est_cost, occ

def clean_float(val, default=0.0):
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.replace('$', '').replace('%', '').strip()
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default

def scan_and_inject_armed_tickers(default_direction="BOTH", force_ticker=None):
    if force_ticker in ["None", "none", ""]:
        force_ticker = None

    try:
        req = urllib.request.urlopen("http://127.0.0.1:8000/api/proximity", timeout=2)
        telemetry = json.loads(req.read().decode()) if req.status == 200 else {}
    except Exception:
        telemetry = {}

    targets_to_inject = []

    if force_ticker:
        info = telemetry.get(force_ticker, {})
        spot = clean_float(info.get("spot") or info.get("spot_price"), default=308.30)
        direction = default_direction if default_direction in ["CALL", "PUT"] else "CALL"
        targets_to_inject.append((force_ticker, direction, spot))
    else:
        for ticker, info in telemetry.items():
            status = str(info.get("status", "")).upper()
            target_val = clean_float(info.get("target"), default=0.0)

            if target_val == 0.0 or str(info.get("target")).upper() in ["NONE", "N/A"]:
                continue

            raw_gap = info.get("gap_pct") or info.get("gap") or 999.0
            gap_pct = clean_float(raw_gap, default=999.0)

            if status == "ARMED" or (0.01 <= gap_pct <= 1.0):
                spot = clean_float(info.get("spot") or info.get("spot_price"), default=16.33)
                direction = "CALL" if spot <= target_val else "PUT"
                targets_to_inject.append((ticker, direction, spot))

    if not targets_to_inject:
        print("[*] Scan complete: No tickers currently in ARMED proximity.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')

    for ticker, direction, spot_price in targets_to_inject:
        cursor.execute("SELECT id FROM trades WHERE ticker = ? AND exit_status = 'ACTIVE'", (ticker,))
        if cursor.fetchone():
            print(f"[!] Ticker {ticker} already active. Skipping.")
            continue

        cso_entry_price, occ_symbol = fetch_live_tradier_option(ticker, direction, spot_price)

        sql = """
            INSERT INTO trades (
                ticker, direction, spot_price, entry_price, option_symbol,
                exit_status, strategy, is_live, 
                cso_cleared, cso_notes, timestamp
            )
            VALUES (?, ?, ?, ?, ?, 'ACTIVE', 'CSO_AUTO_INJECT', 1, 1, ?, ?)
        """
        
        cso_notes = f"OCC: {occ_symbol} | Entry Ask: ${cso_entry_price}"
        cursor.execute(sql, (ticker, direction, spot_price, cso_entry_price, occ_symbol, cso_notes, timestamp))
        print(f"[✓] INJECTED {ticker} -> {direction} | Contract: {occ_symbol} | Entry Ask: ${cso_entry_price}")

    conn.commit()
    conn.close()

    try:
        subprocess.run(["./venv/bin/python3", "src/generate_dashboard_data.py"], check=True)
    except Exception as e:
        print(f"[-] Telemetry compile error: {e}")

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else None
    direction = sys.argv[2] if len(sys.argv) > 2 else "BOTH"
    
    scan_and_inject_armed_tickers(default_direction=direction, force_ticker=target)
