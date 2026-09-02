#!/usr/bin/env python3
import os, sys, argparse, boto3, requests
from datetime import datetime
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr
import src.gex_exit_monitor as gex

def parse_args():
    parser = argparse.ArgumentParser(description="HARM.AI Scoped Position Exit Engine")
    parser.add_argument("-e", "--env", type=str, choices=["SANDBOX", "PROD"], default="PROD")
    parser.add_argument("-f", "--force", action="store_true", help="Force close targeted tickers only")
    parser.add_argument("-tt", "--ticker-target", action="append", default=[], help="TICKER=STOP,TARGET or TICKER=TARGET")
    args = parser.parse_args()

    ticker_brackets = {}
    for entry in args.ticker_target:
        if "=" in entry:
            tkr, val_str = entry.split("=", 1)
            tkr = tkr.strip().upper()
            if "," in val_str:
                parts = val_str.split(",")
                ticker_brackets[tkr] = {'stop': -abs(float(parts[0].strip())), 'target': float(parts[1].strip())}
            else:
                val = float(val_str.strip())
                ticker_brackets[tkr] = {'stop': val if val < 0 else None, 'target': val if val >= 0 else None}
    return ticker_brackets, args.env, args.force

def force_close_position(occ_symbol, ticker, shares, bid_price):
    account_id = os.getenv('TRADIER_ACCOUNT_ID')
    access_token = os.getenv('TRADIER_TOKEN')
    base_url = os.getenv('TRADIER_BASE_URL', 'https://api.tradier.com/v1').rstrip('/')
    
    url = f"{base_url}/accounts/{account_id}/orders"
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    limit_val = max(bid_price, 0.01)
    
    data = {
        "class": "option",
        "symbol": ticker,
        "option_symbol": occ_symbol,
        "side": "sell_to_close",
        "quantity": str(shares),
        "type": "limit",
        "price": f"{limit_val:.2f}",
        "duration": "day"
    }
    
    print(f"[⚡ FORCE CLOSE] Submitting Limit Sell @ ${limit_val:.2f} for {shares}x {occ_symbol}...")
    r = requests.post(url, data=data, headers=headers, timeout=10)
    print(f"[✓ TRADIER RESPONSE] {r.json()}")

def run():
    ticker_brackets, target_env, force_execution = parse_args()
    env_file = '.env.prod' if target_env == "PROD" else '.env.sandbox'
    load_dotenv(env_file, override=True)
    
    account_id = os.getenv('TRADIER_ACCOUNT_ID')
    access_token = os.getenv('TRADIER_TOKEN')
    base_url = os.getenv('TRADIER_BASE_URL', 'https://api.tradier.com/v1').rstrip('/')
    
    # Query live Tradier positions directly
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    res = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers, timeout=5)
    pos_data = res.json().get("positions", {})
    if not pos_data or pos_data == 'null':
        print("[✓] No open positions in account.")
        return
        
    pos_list = pos_data.get("position", [])
    if isinstance(pos_list, dict):
        pos_list = [pos_list]
        
    for p in pos_list:
        occ = p.get('symbol', '')
        qty = int(p.get('quantity', 1))
        cost = float(p.get('cost_basis', 0.0))
        entry = cost / (100.0 * qty) if qty > 0 else 0.0
        ticker = occ[:4].rstrip('0123456789')
        
        # STRICT TICKER SCOPING: Skip any ticker NOT explicitly passed in -tt
        if ticker_brackets and ticker not in ticker_brackets:
            print(f"[🛡️ UNTARGETED] Skipping {ticker} ({occ}) - Not in target list.")
            continue
            
        q_res = requests.get(f"{base_url}/markets/quotes", params={"symbols": occ}, headers=headers).json()
        q = q_res.get("quotes", {}).get("quote", {})
        bid = float(q.get("bid", 0.0) or 0.0)
        pnl_dollar = (bid - entry) * 100.0 * qty
        
        bracket = ticker_brackets.get(ticker, {})
        hit_tp = (bracket.get('target') is not None and pnl_dollar >= bracket['target'])
        hit_sl = (bracket.get('stop') is not None and pnl_dollar <= bracket['stop'])
        
        # Only force close if explicitly targeted AND force flag is on, or bracket is hit
        if (force_execution and ticker in ticker_brackets) or hit_tp or hit_sl:
            print(f"[🚨 CLOSING] {ticker} PnL: ${pnl_dollar:+.2f} | Action Triggered.")
            force_close_position(occ, ticker, qty, bid)

if __name__ == "__main__":
    run()
