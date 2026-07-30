import sqlite3
import json
import time
import os
import argparse
import urllib.request
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'harm_telemetry.db')

def clean_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.replace('$', '').replace(',', '').strip()
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default

def check_portfolio_risk(cursor, max_deployed_capital=5000.0, max_active_positions=6):
    """Verifies overall portfolio risk limits before injecting new capital."""
    cursor.execute("SELECT COUNT(*) FROM trades WHERE exit_status = 'ACTIVE'")
    active_count = cursor.fetchone()[0]
    
    if active_count >= max_active_positions:
        print(f"[RISK BLOCK] Active positions count ({active_count}) meets or exceeds max allowed ({max_active_positions}).")
        return False
        
    return True

def generate_occ_symbol(ticker, spot, direction, strategy="ATM"):
    """
    Dynamically generates OCC option symbols based on requested fill strategy.
    Strategies:
      - ATM: Round to nearest $5/$1 strike
      - ITM: 1 strike in-the-money
      - OTM1: 1 strike out-of-the-money
    """
    # Expiration: Next upcoming Friday (or today if Friday)
    today = datetime.now()
    days_until_friday = (4 - today.weekday()) % 7
    friday = today + timedelta(days=days_until_friday)
    exp_str = friday.strftime("%y%m%d")
    
    # Base Strike rounding logic
    strike_step = 5.0 if spot >= 50.0 else 1.0
    base_strike = round(spot / strike_step) * strike_step
    
    if direction == "CALL":
        if strategy == "ITM":
            strike = max(strike_step, base_strike - strike_step)
        elif strategy == "OTM1":
            strike = base_strike + strike_step
        else: # ATM
            strike = base_strike
        opt_type = "C"
    else: # PUT
        if strategy == "ITM":
            strike = base_strike + strike_step
        elif strategy == "OTM1":
            strike = max(strike_step, base_strike - strike_step)
        else: # ATM
            strike = base_strike
        opt_type = "P"
        
    strike_int = int(round(strike * 1000))
    occ_symbol = f"{ticker.upper()}{exp_str}{opt_type}{strike_int:08d}"
    return occ_symbol, strike

def scan_and_inject(aperture_pct=1.5, fill_strategy="ATM", force_ticker=None, direction_override="CALL"):
    """Scans proximity matrix or forces injection subject to risk evaluation."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Run Pre-Injection Risk Checks
    if not check_portfolio_risk(cursor):
        conn.close()
        return

    # 2. Fetch Live Proximity Telemetry
    try:
        req = urllib.request.urlopen("http://127.0.0.1:8000/api/proximity", timeout=2)
        telemetry = json.loads(req.read().decode()) if req.status == 200 else {}
    except Exception:
        telemetry = {}

    targets_to_inject = []

    if force_ticker:
        info = telemetry.get(force_ticker, {})
        spot = clean_float(info.get("spot") or info.get("spot_price"), default=100.0)
        direction = direction_override if direction_override in ["CALL", "PUT"] else "CALL"
        targets_to_inject.append((force_ticker, direction, spot))
    else:
        for ticker, info in telemetry.items():
            gap_pct = clean_float(info.get("gap_pct") or info.get("gap"), default=999.0)
            status = str(info.get("status", "")).upper()
            
            # Aperture check: If status is ARMED or gap is within user-specified aperture
            if status == "ARMED" or (0.0 <= gap_pct <= aperture_pct):
                spot = clean_float(info.get("spot") or info.get("spot_price"), default=100.0)
                target_val = clean_float(info.get("target"), default=spot)
                direction = "CALL" if spot <= target_val else "PUT"
                targets_to_inject.append((ticker, direction, spot))

    if not targets_to_inject:
        print(f"[*] Scan complete: No tickers within {aperture_pct}% aperture window.")
        conn.close()
        return

    # 3. Inject Valid Candidates
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    
    for ticker, direction, spot_price in targets_to_inject:
        cursor.execute("SELECT id FROM trades WHERE ticker = ? AND exit_status = 'ACTIVE'", (ticker,))
        if cursor.fetchone():
            print(f"[!] Ticker {ticker} is already active. Skipping duplicate injection.")
            continue

        occ_symbol, strike = generate_occ_symbol(ticker, spot_price, direction, strategy=fill_strategy)
        
        # Estimate premium cost & initial risk limits
        estimated_cost = round(spot_price * 0.03, 2) # Est. 3% option cost
        stop_loss = round(estimated_cost * 0.80, 2)   # 20% max contract risk
        take_profit = round(estimated_cost * 1.50, 2) # 50% take profit target

        cursor.execute('''
            INSERT INTO trades (
                ticker, direction, spot_price, entry_price, shares, exit_status, 
                strategy, option_symbol, occ_symbol, stop_loss, take_profit, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            ticker, direction, spot_price, estimated_cost, 1, 'ACTIVE', 
            f'CSO_{fill_strategy}', occ_symbol, occ_symbol, stop_loss, take_profit, timestamp
        ))
        
        print(f"[✓] INJECTED: {ticker} ({direction}) | Fill: {fill_strategy} | Option: {occ_symbol} | Spot: ${spot_price:.2f}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CSO Risk & Aperture Auto-Injector")
    parser.add_argument("--aperture", type=float, default=1.5, help="Proximity gap percentage aperture limit (e.g. 2.0 for 2%%)")
    parser.add_argument("--fill-strategy", type=str, choices=["ATM", "ITM", "OTM1"], default="ATM", help="Contract strike strategy")
    parser.add_argument("--force", type=str, default=None, help="Force inject specific ticker (bypasses proximity)")
    parser.add_argument("--direction", type=str, choices=["CALL", "PUT"], default="CALL", help="Direction for forced ticker")
    
    args = parser.parse_args()
    scan_and_inject(
        aperture_pct=args.aperture, 
        fill_strategy=args.fill_strategy, 
        force_ticker=args.force, 
        direction_override=args.direction
    )
