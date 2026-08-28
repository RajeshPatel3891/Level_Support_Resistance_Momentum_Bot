#!/usr/bin/env python3
"""
HARM.AI // LIVE PNL, FILL QUALITY & 0-100 CONFIDENCE MONITOR
===============================================================================
Polls active positions, computes persistent fill scores, and displays live
composite trade confidence (0-100 scale) based on microstructure, VWAP,
SPY/QQQ market beta, and time-of-day liquidity gates.
"""

import os
import re
import time
import json
import requests
from check_and_close_target import calculate_active_trade_confidence, calculate_fill_quality_score

def load_gex_levels():
    try:
        res = requests.get("http://localhost:8080/api/proximity", timeout=1.5)
        if res.status_code == 200 and res.text.strip():
            data = res.json()
            if isinstance(data, dict):
                return data
    except Exception:
        pass

    levels_path = "trading_levels.json"
    if os.path.exists(levels_path):
        try:
            with open(levels_path, "r") as f:
                data = json.load(f)
                return data.get("levels", data) if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}

def parse_option_symbol(symbol):
    match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", symbol)
    if match:
        ticker, date_str, opt_type_letter, strike_raw = match.groups()
        opt_type = "CALL" if opt_type_letter == "C" else "PUT"
        strike = float(strike_raw) / 1000.0
        return ticker, f"{opt_type} ${strike:.2f}", opt_type
    return symbol, "STOCK", "STOCK"

def check_gex_engagement(underlying, opt_type, underlying_spot, gex_data):
    if not gex_data or underlying_spot <= 0:
        return "⚠️ NO DATA"

    ticker_gex = None
    for k, v in gex_data.items():
        if k.upper() == underlying.upper() and isinstance(v, dict):
            ticker_gex = v
            break
            
    if not ticker_gex:
        return "⚠️ NO LEVEL"
    
    # Dynamic target resolution across key variants
    call_target = 0.0
    put_target = 0.0

    if "resistance_zone" in ticker_gex and isinstance(ticker_gex["resistance_zone"], list) and len(ticker_gex["resistance_zone"]) > 0:
        call_target = float(ticker_gex["resistance_zone"][0])
    elif "call_target" in ticker_gex or "call_strike" in ticker_gex or "target" in ticker_gex:
        call_target = float(ticker_gex.get("call_target") or ticker_gex.get("call_strike") or ticker_gex.get("target") or 0.0)

    if "support_zone" in ticker_gex and isinstance(ticker_gex["support_zone"], list) and len(ticker_gex["support_zone"]) > 1:
        put_target = float(ticker_gex["support_zone"][1])
    elif "put_target" in ticker_gex or "put_strike" in ticker_gex:
        put_target = float(ticker_gex.get("put_target") or ticker_gex.get("put_strike") or 0.0)

    if opt_type == "CALL" and call_target > 0:
        dist_pct = ((call_target - underlying_spot) / underlying_spot) * 100.0
        if underlying_spot >= call_target:
            return "🔥 ENGAGED"
        elif abs(dist_pct) <= 0.5:
            return "⚡ ARMED"
        else:
            return f"🎯 {dist_pct:+.1f}% TGT"

    elif opt_type == "PUT" and put_target > 0:
        dist_pct = ((underlying_spot - put_target) / underlying_spot) * 100.0
        if underlying_spot <= put_target:
            return "🔥 ENGAGED"
        elif abs(dist_pct) <= 0.5:
            return "⚡ ARMED"
        else:
            return f"🎯 {dist_pct:+.1f}% TGT"

    return "⚠️ NO LEVEL"

def safe_fetch_json(url, headers, params=None, timeout=3.0):
    try:
        r = requests.get(url, headers=headers, params=params, timeout=timeout)
        if r.status_code == 200 and r.text.strip():
            return r.json()
    except Exception:
        pass
    return {}

def poll_pnl_loop(env="SANDBOX", interval=2.5):
    env_upper = env.upper()
    
    if env_upper in ["PROD", "PRODUCTION", "LIVE"]:
        token = os.getenv("TRADIER_TOKEN", "fyR75AACwlIYhkMyev1doRh6gnSr")
        acct = os.getenv("TRADIER_ACCOUNT_ID", "6YB87601")
        base_url = "https://api.tradier.com/v1"
        display_env = "PROD"
    else:
        token = os.getenv("TRADIER_SANDBOX_TOKEN", "hcY1t0sY8RZmcsfVjQCA41ecAkFT")
        acct = "VA83416608"
        base_url = "https://sandbox.tradier.com/v1"
        display_env = "SANDBOX"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    while True:
        try:
            os.system('clear')
            gex_levels = load_gex_levels()
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S ET")
            print("=========================================================================================================================")
            print(f"📊 LIVE PNL, FILL QUALITY & 0-100 CONFIDENCE MONITOR | {display_env} ({acct}) | {timestamp}")
            print("=========================================================================================================================")

            pos_res = safe_fetch_json(f"{base_url}/accounts/{acct}/positions", headers=headers)
            positions = pos_res.get("positions") if isinstance(pos_res, dict) else None
            
            if positions == "null" or not positions or not isinstance(positions, dict):
                positions = []
            else:
                positions = positions.get("position", [])
                if isinstance(positions, dict):
                    positions = [positions]

            if positions:
                option_symbols = [p.get("symbol") for p in positions if isinstance(p, dict) and p.get("symbol")]
                underlying_symbols = list(set([parse_option_symbol(s)[0] for s in option_symbols]))
                all_query_symbols = ",".join(option_symbols + underlying_symbols + ["SPY", "QQQ"])

                quotes_dict = {}
                q_res = safe_fetch_json(f"{base_url}/markets/quotes", headers=headers, params={"symbols": all_query_symbols})
                if isinstance(q_res, dict):
                    quotes = q_res.get("quotes", {}).get("quote", [])
                    if isinstance(quotes, dict): quotes = [quotes]
                    for q in quotes:
                        if isinstance(q, dict) and q.get("symbol"):
                            quotes_dict[q.get("symbol")] = {
                                "last": q.get("last", 0) or q.get("close", 0) or 0,
                                "bid": q.get("bid", 0) or q.get("last", 0) or 0,
                                "ask": q.get("ask", 0) or q.get("last", 0) or 0,
                                "vwap": q.get("vwap", 0) or q.get("last", 0) or 0,
                                "change_pct": q.get("change_percentage", 0.0) or 0.0
                            }

                spy_change = quotes_dict.get("SPY", {}).get("change_pct", 0.0)
                qqq_change = quotes_dict.get("QQQ", {}).get("change_pct", 0.0)

                total_cost = 0
                total_val = 0

                print(f"{'SYMBOL':<20} | {'TYPE':<11} | {'QTY':<3} | {'COST':<8} | {'BID/ASK':<11} | {'CONF (0-100)':<14} | {'SCORE':<6} | {'GEX EXIT':<11} | {'LIVE PNL'}")
                print("-" * 125)

                for p in positions:
                    if not isinstance(p, dict): continue
                    sym = p.get("symbol")
                    underlying, opt_desc, opt_type = parse_option_symbol(sym)
                    qty = float(p.get("quantity", 0))
                    cost_basis = float(p.get("cost_basis", 0))
                    entry_price = (cost_basis / (100.0 * qty)) if qty > 0 else 0.0

                    opt_quote = quotes_dict.get(sym, {})
                    opt_bid = float(opt_quote.get("bid", 0) or 0)
                    opt_ask = float(opt_quote.get("ask", 0) or 0)
                    
                    stock_quote = quotes_dict.get(underlying, {})
                    underlying_spot = float(stock_quote.get("last", 0) or 0)
                    vwap = float(stock_quote.get("vwap", underlying_spot) or underlying_spot)

                    gex_status = check_gex_engagement(underlying, opt_type, underlying_spot, gex_levels)

                    current_val = opt_bid * qty * 100 if opt_bid > 0 else cost_basis
                    pnl = current_val - cost_basis
                    pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0

                    is_call = (opt_type == "CALL")
                    conf_score, conf_action, _ = calculate_active_trade_confidence(
                        entry_price, opt_bid, opt_ask, underlying_spot, vwap, spy_change, qqq_change, is_call=is_call
                    )

                    if conf_score >= 80:
                        conf_str = f"🟢 {conf_score:.0f}/100"
                    elif conf_score >= 50:
                        conf_str = f"🟡 {conf_score:.0f}/100"
                    else:
                        conf_str = f"🔴 {conf_score:.0f}/100"

                    fill_score = calculate_fill_quality_score(entry_price, opt_bid, opt_ask, side="buy")
                    score_str = f"{fill_score:.1f}/10"

                    total_cost += cost_basis
                    total_val += current_val

                    pnl_str = f"+${pnl:.2f} (+{pnl_pct:.2f}%)" if pnl >= 0 else f"-${abs(pnl):.2f} ({pnl_pct:.2f}%)"
                    bid_ask_str = f"${opt_bid:.2f}/${opt_ask:.2f}"
                    print(f"{sym:<20} | {opt_desc:<11} | {qty:<3.0f} | ${cost_basis:<7.2f} | {bid_ask_str:<11} | {conf_str:<14} | {score_str:<6} | {gex_status:<11} | {pnl_str}")

                total_pnl = total_val - total_cost
                total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
                tot_str = f"+${total_pnl:.2f} (+{total_pnl_pct:.2f}%)" if total_pnl >= 0 else f"-${abs(total_pnl):.2f} ({total_pnl_pct:.2f}%)"

                print("-" * 125)
                print(f"AGGREGATE PORTFOLIO SUMMARY | Total Invested: ${total_cost:.2f} | Current Value: ${total_val:.2f} | Total PnL: {tot_str}")
            else:
                print("No open positions active.")

            print("\n==========================================================================================================")
            print("📄 TODAY'S PENDING / EXECUTED ORDERS & FILL QUALITY SCORES")
            print("==========================================================================================================")

            ord_res = safe_fetch_json(f"{base_url}/accounts/{acct}/orders", headers=headers)
            orders = ord_res.get("orders") if isinstance(ord_res, dict) else None
            
            if orders == "null" or not orders or not isinstance(ord_res, dict):
                orders = []
            else:
                orders = orders.get("order", [])
                if isinstance(orders, dict):
                    orders = [orders]

            if orders:
                for o in list(reversed(orders))[:5]:
                    if not isinstance(o, dict): continue
                    sym = o.get('symbol', '')
                    _, opt_desc, _ = parse_option_symbol(sym)
                    exec_price = float(o.get('avg_fill_price', 0) or 0)
                    side = o.get('side', 'buy_to_open')

                    q = quotes_dict.get(sym, {}) if 'quotes_dict' in locals() else {}
                    bid = float(q.get('bid', 0) or 0)
                    ask = float(q.get('ask', 0) or 0)

                    score = calculate_fill_quality_score(exec_price, bid, ask, side=side)
                    score_display = f"{score:.1f}/10" if exec_price > 0 else "N/A"

                    print(f"ID: {o.get('id')} | Symbol: {sym:<20} | Side: {side:<13} | Status: {o.get('status', 'N/A'):<8} | Exec: ${exec_price:<5.2f} | Fill Score: {score_display}")
            else:
                print("No active or filled orders today.")

        except Exception as e:
            print(f"[!] Polling loop warning: {e}")

        time.sleep(interval)

if __name__ == "__main__":
    import sys
    target_env = sys.argv[1] if len(sys.argv) > 1 else "SANDBOX"
    poll_pnl_loop(target_env, interval=2.5)
