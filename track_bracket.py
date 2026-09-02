#!/usr/bin/env python3
"""
HARM.AI // ISOLATED BRACKET MONITOR
===============================================================================
Usage:
  python3 track_bracket.py --symbol RIVN --stop -10.00 --target 15.00
  python3 track_bracket.py --symbol MARA --stop -8.00 --target 4.00
"""

import os, sys, time, argparse, requests
from dotenv import load_dotenv

load_dotenv(".env.prod", override=True)

TOKEN = os.getenv("TRADIER_TOKEN")
ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "6YB87601")
BASE_URL = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip("/")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

def parse_args():
    parser = argparse.ArgumentParser(description="Isolated Single-Ticker Bracket Monitor")
    parser.add_argument("-s", "--symbol", type=str, required=True, help="Underlying ticker (e.g., RIVN, MARA)")
    parser.add_argument("--stop", type=float, default=None, help="Stop loss in total dollar terms (e.g., -10.00)")
    parser.add_argument("--target", type=float, default=None, help="Take profit in total dollar terms (e.g., 15.00)")
    parser.add_argument("-i", "--interval", type=int, default=5, help="Polling interval in seconds")
    return parser.parse_args()

def get_position_details(target_ticker):
    res = requests.get(f"{BASE_URL}/accounts/{ACCOUNT_ID}/positions", headers=HEADERS, timeout=5)
    if res.status_code != 200:
        return None
    pos_data = res.json().get("positions", {})
    if not pos_data or pos_data == 'null':
        return None
    pos_list = pos_data.get("position", [])
    if isinstance(pos_list, dict):
        pos_list = [pos_list]
    
    for p in pos_list:
        occ = p.get("symbol", "")
        # Match by root symbol or full OCC string
        if occ.startswith(target_ticker.upper()) or target_ticker.upper() in occ:
            qty = int(p.get("quantity", 1))
            cost = float(p.get("cost_basis", 0.0))
            entry = (cost / (100.0 * qty)) if qty > 0 else 0.0
            return {
                "occ_symbol": occ,
                "shares": qty,
                "cost_basis": cost,
                "entry_price": entry
            }
    return None

def close_position(occ, ticker, shares, bid):
    limit_val = max(bid, 0.01)
    payload = {
        "class": "option",
        "symbol": ticker,
        "option_symbol": occ,
        "side": "sell_to_close",
        "quantity": str(shares),
        "type": "limit",
        "price": f"{limit_val:.2f}",
        "duration": "day"
    }
    print(f"\n[🚨 EXECUTING CLOSE] Sending limit sell @ ${limit_val:.2f} for {shares}x {occ}...")
    res = requests.post(f"{BASE_URL}/accounts/{ACCOUNT_ID}/orders", data=payload, headers=HEADERS, timeout=10)
    print(f"[✓ TRADIER RESPONSE]: {res.json()}")
    
    # Auto-reconcile database
    if os.path.exists("fix_sync.py"):
        os.system("python3 fix_sync.py")

def main():
    args = parse_args()
    ticker = args.symbol.upper()
    stop_threshold = -abs(args.stop) if args.stop is not None else None
    target_threshold = abs(args.target) if args.target is not None else None

    print(f"[*] Initializing bracket tracker for {ticker} | Bracket: [Stop: {stop_threshold} | Target: +{target_threshold}]")

    while True:
        pos = get_position_details(ticker)
        if not pos:
            print(f"[✓] No open position found on Tradier for {ticker}. Exiting monitor.")
            break

        occ = pos["occ_symbol"]
        shares = pos["shares"]
        entry = pos["entry_price"]

        # Fetch live quote
        q_res = requests.get(f"{BASE_URL}/markets/quotes", params={"symbols": occ}, headers=HEADERS, timeout=5)
        q = q_res.json().get("quotes", {}).get("quote", {})
        bid = float(q.get("bid", 0.0) or 0.0)
        ask = float(q.get("ask", 0.0) or 0.0)

        pnl_dollar = round((bid - entry) * 100.0 * shares, 2)
        pnl_pct = ((bid - entry) / entry * 100.0) if entry > 0 else 0.0

        sys.stdout.write(f"\r[{time.strftime('%H:%M:%S')}] {occ} ({shares}x) | Entry: ${entry:.2f} | Bid/Ask: ${bid:.2f}/${ask:.2f} | Realized PnL: ${pnl_dollar:+.2f} ({pnl_pct:+.1f}%)   ")
        sys.stdout.flush()

        # Check triggers
        if target_threshold is not None and pnl_dollar >= target_threshold:
            print(f"\n[🎯 TARGET REACHED] PnL (${pnl_dollar:+.2f}) >= +${target_threshold:.2f}")
            close_position(occ, ticker, shares, bid)
            break

        if stop_threshold is not None and pnl_dollar <= stop_threshold:
            print(f"\n[🛑 STOP LOSS TRIGGERED] PnL (${pnl_dollar:+.2f}) <= ${stop_threshold:.2f}")
            close_position(occ, ticker, shares, bid)
            break

        time.sleep(args.interval)

if __name__ == "__main__":
    main()
