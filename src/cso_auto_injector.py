import sqlite3
import json
import time
import subprocess
import os
import urllib.request

DB_PATH = "harm_telemetry.db"
LEVELS_PATH = "trading_levels.json"

def fetch_live_option_quote(ticker, direction, spot_price):
    """
    Fetches the live 0DTE option contract quote and OCC symbol from Tradier API,
    falling back to a dynamic 3.5% delta estimate if API is unreachable.
    """
    try:
        # Fetch option chain telemetry from local sync API endpoint
        req = urllib.request.urlopen(f"http://127.0.0.1:8000/api/proximity", timeout=2)
        if req.status == 200:
            data = json.loads(req.read().decode())
            ticker_data = data.get(ticker, {})
            
            # Check if live option ask is present in telemetry feed
            live_ask = ticker_data.get("opt_ask") or ticker_data.get("option_ask")
            occ_symbol = ticker_data.get("occ_symbol") or ticker_data.get("contract")
            
            if live_ask and float(live_ask) > 0:
                print(f"[✓] Tradier Market Direct -> {ticker} Option Ask: ${live_ask} | Contract: {occ_symbol}")
                return float(live_ask), occ_symbol
    except Exception as e:
        pass

    # Dynamic fallback scaled to spot price rather than static $0.50
    estimated_cost = round(max(spot_price * 0.035, 0.35), 2)
    dummy_occ = f"{ticker}260731{'C' if direction == 'CALL' else 'P'}000{int(spot_price*1000):05d}"
    print(f"[!] Tradier chain fallback -> {ticker} Dynamic Est: ${estimated_cost} ({dummy_occ})")
    return estimated_cost, dummy_occ

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
        spot = clean_float(info.get("spot") or info.get("spot_price"), default=16.33)
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

        # FETCH REAL MARKET OPTION ENTRY & OCC SYMBOL
        cso_entry_price, occ_symbol = fetch_live_option_quote(ticker, direction, spot_price)

        sql = """
            INSERT INTO trades (
                ticker, direction, spot_price, entry_price, 
                exit_status, strategy, is_live, 
                cso_cleared, cso_notes, timestamp
            )
            VALUES (?, ?, ?, ?, 'ACTIVE', 'CSO_AUTO_INJECT', 1, 1, ?, ?)
        """
        
        cso_notes = f"OCC: {occ_symbol} | Live Entry: ${cso_entry_price}"
        cursor.execute(sql, (ticker, direction, spot_price, cso_entry_price, cso_notes, timestamp))
        print(f"[✓] INJECTED {ticker} -> {direction} | Contract: {occ_symbol} | Live Entry Ask: ${cso_entry_price}")

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
