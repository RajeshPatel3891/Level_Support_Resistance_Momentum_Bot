#!/usr/bin/env python3
import os, sys, time, requests
from dotenv import load_dotenv

BASE_URL = "http://localhost:8000/v1"
ACCOUNT_ID = "6YB87601"
HEADERS = {"Authorization": "Bearer mock_test_token", "Accept": "application/json"}

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
        # The mock server was patched to return "NKE260904P00080000" in the symbol field
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

def main():
    ticker = "NKE"
    stop_threshold = -10.00
    target_threshold = 8.00
    print(f"[*] Initializing REPLAY bracket tracker for {ticker} | Bracket: [Stop: {stop_threshold} | Target: +{target_threshold}]")

    while True:
        pos = get_position_details(ticker)
        if not pos:
            print(f"\n[✓] No open position found on Tradier for {ticker}. Exiting monitor.")
            break

        occ = pos["occ_symbol"]
        shares = pos["shares"]
        entry = pos["entry_price"]

        q_res = requests.get(f"{BASE_URL}/markets/quotes", params={"symbols": occ}, headers=HEADERS, timeout=5)
        q = q_res.json().get("quotes", {}).get("quote", {})
        bid = float(q.get("bid", 0.0) or 0.0)
        ask = float(q.get("ask", 0.0) or 0.0)

        pnl_dollar = round((bid - entry) * 100.0 * shares, 2)
        pnl_pct = ((bid - entry) / entry * 100.0) if entry > 0 else 0.0

        sys.stdout.write(f"\r[{time.strftime('%H:%M:%S')}] {occ} ({shares}x) | Entry: ${entry:.2f} | Bid/Ask: ${bid:.2f}/${ask:.2f} | PnL: ${pnl_dollar:+.2f} ({pnl_pct:+.1f}%)   ")
        sys.stdout.flush()

        if target_threshold is not None and pnl_dollar >= target_threshold:
            print(f"\n[🚀 TARGET HIT] PnL {pnl_dollar} >= {target_threshold}")
            close_position(occ, ticker, shares, bid)
            time.sleep(2)
        elif stop_threshold is not None and pnl_dollar <= stop_threshold:
            print(f"\n[🛑 STOP HIT] PnL {pnl_dollar} <= {stop_threshold}")
            close_position(occ, ticker, shares, bid)
            time.sleep(2)
            
        time.sleep(2)

if __name__ == "__main__":
    main()
