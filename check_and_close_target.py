#!/usr/bin/env python3
"""
HARM.AI // PERSISTENT FILL QUALITY & TRADE CONFIDENCE CLOSE ENGINE
===============================================================================
Evaluates active positions against a 5-factor weighted confidence model
(Entry Microstructure, VWAP Alignment, Market Beta, Tape Acceleration, and TOD).
Enforces bracket stops/targets and exits trades when Confidence Score drops below 50.0.

Usage Examples:
  # Standard Bracket Exit (Sandbox):
  python3 check_and_close_target.py --env SANDBOX -tt RIVN=-50.00

  # Force Close (Bypasses market order and places aggressive Bid limit order):
  python3 check_and_close_target.py --env SANDBOX --force -tt RIVN=-50.00

  # Production Bracket Exit:
  python3 check_and_close_target.py --env PROD -tt SOFI=-16.00,20.00
"""

import os
import sys
import argparse
import boto3
import requests
from datetime import datetime
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr
import src.gex_exit_monitor as gex

def calculate_fill_quality_score(fill_price: float, bid: float, ask: float, side: str = "sell") -> float:
    """
    Calculates Fill Quality Score on a 0.0 to 10.0 scale based on market microstructure.
    - 10.0 = Best possible fill (Bid on sell, Ask on buy).
    - 5.0  = Midpoint fill.
    - 0.0  = Worst possible fill (Ask on sell, Bid on buy).
    """
    if ask <= bid or fill_price <= 0:
        return 0.0
    spread = ask - bid
    if side.lower() in ["sell", "sell_to_close"]:
        score = ((fill_price - bid) / spread) * 10.0
    else:
        score = ((ask - fill_price) / spread) * 10.0
    return round(max(0.0, min(10.0, score)), 1)

def get_live_quote(symbol, base_url=None, token=None):
    if not base_url:
        base_url = os.getenv('TRADIER_BASE_URL', 'https://sandbox.tradier.com/v1').rstrip('/')
    if not token:
        token = os.getenv('TRADIER_TOKEN', os.getenv('TRADIER_ACCESS_TOKEN'))

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        res = requests.get(f"{base_url}/markets/quotes", params={"symbols": symbol}, headers=headers, timeout=3)
        if res.status_code == 200:
            q = res.json().get("quotes", {}).get("quote", {})
            return q[0] if isinstance(q, list) and q else (q if isinstance(q, dict) else {})
    except Exception:
        pass
    return {}

def calculate_active_trade_confidence(entry_price, bid, ask, spot, vwap, spy_change, qqq_change, is_call=True) -> tuple:
    """
    Computes 0-100 Confidence Score based on market indicators & entry microstructure.
    Returns (score: float, action: str, checklist: dict).
    """
    checklist = {}
    total_score = 0.0

    # 1. Entry Microstructure (25% Weight) - Rewards fills closer to Bid
    spread = ask - bid if ask > bid else 0.01
    if spread > 0 and entry_price > 0:
        fill_dist_from_bid = entry_price - bid
        micro_score = max(0.0, min(1.0, 1.0 - (fill_dist_from_bid / spread))) * 25.0
    else:
        micro_score = 12.5
    checklist['entry_microstructure'] = round(micro_score, 1)
    total_score += micro_score

    # 2. VWAP Slope Alignment (25% Weight)
    if (is_call and spot >= vwap) or (not is_call and spot <= vwap):
        vwap_score = 25.0
    else:
        vwap_score = 0.0
    checklist['vwap_alignment'] = vwap_score
    total_score += vwap_score

    # 3. Market Beta Confluence (20% Weight)
    if is_call and (spy_change >= -0.05 and qqq_change >= -0.05):
        beta_score = 20.0
    elif not is_call and (spy_change <= 0.05 and qqq_change <= 0.05):
        beta_score = 20.0
    else:
        beta_score = 0.0
    checklist['beta_confluence'] = beta_score
    total_score += beta_score

    # 4. Tape Acceleration / Spread Tightness (15% Weight)
    spread_pct = (spread / ask) if ask > 0 else 1.0
    tape_score = 15.0 if spread_pct <= 0.04 else 5.0
    checklist['tape_acceleration'] = tape_score
    total_score += tape_score

    # 5. Time-of-Day Liquidity Window (15% Weight)
    now_hour = datetime.now().hour
    now_min = datetime.now().minute
    time_float = now_hour + (now_min / 60.0)
    if (9.5 <= time_float <= 11.5) or (13.5 <= time_float <= 16.0):
        tod_score = 15.0
    else:
        tod_score = 0.0  # Mid-day lull penalty
    checklist['time_of_day'] = tod_score
    total_score += tod_score

    # Decision Matrix
    if total_score < 50.0:
        action = "FORCE_SELL"
    elif total_score < 75.0:
        action = "CAUTION_HOLD"
    else:
        action = "HIGH_CONVICTION_HOLD"

    return round(total_score, 1), action, checklist

def parse_args():
    parser = argparse.ArgumentParser(description="HARM.AI Persistent Confidence & Bracket Exit Helper")
    
    parser.add_argument(
        "-e", "--env",
        type=str,
        choices=["SANDBOX", "PROD"],
        default="SANDBOX",
        help="Target environment (SANDBOX or PROD). Defaults to SANDBOX."
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Force close using an aggressive limit order at active Bid price."
    )
    parser.add_argument(
        "default_target",
        type=float,
        nargs="?",
        default=None,
        help="Default profit target in dollars for unflagged tickers"
    )
    parser.add_argument(
        "-t", "--target",
        type=float,
        default=None,
        help="Default profit target flag"
    )
    parser.add_argument(
        "-tt", "--ticker-target",
        action="append",
        default=[],
        help="Per-ticker bracket: TICKER=STOP,TARGET or TICKER=-STOP or TICKER=TARGET"
    )

    args = parser.parse_args()

    global_target = None
    if args.target is not None:
        global_target = args.target
    elif args.default_target is not None:
        global_target = args.default_target

    ticker_brackets = {}
    for entry in args.ticker_target:
        if "=" in entry:
            tkr, val_str = entry.split("=", 1)
            tkr = tkr.strip().upper()
            val_str = val_str.strip()
            
            if "," in val_str:
                parts = val_str.split(",")
                try:
                    stop_val = float(parts[0].strip())
                    target_val = float(parts[1].strip())
                    stop_val = -abs(stop_val) if stop_val != 0 else 0.0
                    ticker_brackets[tkr] = {'stop': stop_val, 'target': target_val}
                except ValueError:
                    print(f"[!] Invalid numeric bracket format for '{entry}'. Skipping.")
            else:
                try:
                    val = float(val_str)
                    if val < 0:
                        ticker_brackets[tkr] = {'stop': val, 'target': None}
                    else:
                        ticker_brackets[tkr] = {'stop': None, 'target': val}
                except ValueError:
                    print(f"[!] Invalid numeric target/stop for '{entry}'. Skipping.")

    return global_target, ticker_brackets, args.env, args.force

def force_close_position(occ_symbol, ticker, shares, bid_price, ask_price=0.0):
    account_id = os.getenv('TRADIER_ACCOUNT_ID')
    access_token = os.getenv('TRADIER_TOKEN', os.getenv('TRADIER_ACCESS_TOKEN'))
    base_url = os.getenv('TRADIER_BASE_URL', 'https://sandbox.tradier.com/v1').rstrip('/')
    
    url = f"{base_url}/accounts/{account_id}/orders"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    
    limit_val = max(bid_price, 0.01)
    limit_price = f"{limit_val:.2f}"
    
    data = {
        "class": "option",
        "symbol": ticker,
        "option_symbol": occ_symbol,
        "side": "sell_to_close",
        "quantity": str(shares),
        "type": "limit",
        "price": limit_price,
        "duration": "day"
    }
    
    print(f"[⚡ FORCE CLOSE] Submitting Limit Sell @ ${limit_price} for {shares}x {occ_symbol}...")
    try:
        r = requests.post(url, data=data, headers=headers, timeout=10)
        if r.status_code == 200:
            print(f"[✓ FORCE SUCCESS] Order placed cleanly: {r.json()}")
            if ask_price > bid_price:
                fill_score = calculate_fill_quality_score(limit_val, bid_price, ask_price, side="sell")
                print(f"[✓ EXIT FILLED] {ticker} ({occ_symbol}) closed @ ${limit_val:.2f} | Fill Quality Score: {fill_score}/10.0")
            return True
        else:
            print(f"[!] Force close failed ({r.status_code}): {r.text}")
            return False
    except Exception as e:
        print(f"[!] Exception during force close: {e}")
        return False

def fetch_tradier_direct_positions(account_id, access_token, base_url):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }
    endpoint = f"{base_url.rstrip('/')}/accounts/{account_id}/positions"
    
    try:
        resp = requests.get(endpoint, headers=headers, timeout=10)
        if resp.status_code != 200:
            print(f"[!] Tradier Direct API error ({resp.status_code}): {resp.text}")
            return []
        
        data = resp.json().get('positions', {})
        if not data or data == 'null':
            return []
            
        pos_list = data.get('position', [])
        if isinstance(pos_list, dict):
            pos_list = [pos_list]

        items = []
        for p in pos_list:
            occ_symbol = p.get('symbol', '')
            cost_basis = float(p.get('cost_basis', 0.0))
            quantity = abs(int(float(p.get('quantity', 1))))
            entry_price = round(cost_basis / (100.0 * quantity), 4) if quantity > 0 else 0.0
            
            ticker = occ_symbol[:4].rstrip('0123456789') if len(occ_symbol) >= 4 else occ_symbol

            items.append({
                'ticker': ticker,
                'occ_symbol': occ_symbol,
                'entry_price': entry_price,
                'shares': quantity,
                'source': 'TRADIER_DIRECT'
            })

        return items

    except Exception as e:
        print(f"[!] Failed to query Tradier positions directly: {e}")
        return []

def scan_and_close_targets(global_target, ticker_brackets, force_execution=False):
    account_id = os.getenv('TRADIER_ACCOUNT_ID')
    access_token = os.getenv('TRADIER_TOKEN', os.getenv('TRADIER_ACCESS_TOKEN'))
    base_url = os.getenv('TRADIER_BASE_URL', 'https://sandbox.tradier.com/v1').rstrip('/')

    active_items = []

    # 1. Primary Source: Query DynamoDB
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table_name = os.getenv('DYNAMODB_TABLE', 'HarmonizedTrades')
        table = dynamodb.Table(table_name)
        res = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        active_items = res.get('Items', [])
    except Exception as e:
        print(f"[!] DynamoDB scan failed ({e}). Attempting direct Tradier fallback...")

    # 2. Fallback Source: Direct Tradier Broker Scan
    if not active_items and account_id and access_token:
        print(f"[*] Checking Tradier Account ({account_id}) directly...")
        active_items = fetch_tradier_direct_positions(account_id, access_token, base_url)

    if not active_items:
        print(f"[✓] No active positions open in DynamoDB or Tradier Broker.")
        return

    print("=" * 85)
    print(f"🔍 HARM.AI // CONFIDENCE CHECKLIST & CLOSE ENGINE | Auditing {len(active_items)} Position(s)")
    print("=" * 85)

    spy_q = get_live_quote("SPY", base_url, access_token)
    qqq_q = get_live_quote("QQQ", base_url, access_token)
    spy_change = float(spy_q.get("change_percentage", 0.0) or 0.0)
    qqq_change = float(qqq_q.get("change_percentage", 0.0) or 0.0)

    for item in active_items:
        ticker = item.get('ticker', '').strip().upper()
        occ_symbol = item.get('occ_symbol', ticker)
        entry_price = float(item.get('entry_price', 0.0))
        shares = int(float(item.get('shares', 1)))

        if entry_price <= 0 or not occ_symbol:
            continue

        default_bracket = {'stop': None, 'target': global_target}
        bracket = ticker_brackets.get(ticker, default_bracket)
        stop_loss = bracket['stop']
        profit_target = bracket['target']

        # Fetch live Bid & Ask explicitly
        bid, ask, active_url = gex.get_live_bid_ask(occ_symbol)
        if bid <= 0 and ask <= 0:
            print(f"[!] Unable to fetch valid quote for {occ_symbol}. Skipping.")
            continue

        # Fetch underlying stock quote for VWAP and spot
        stock_q = get_live_quote(ticker, base_url, access_token)
        spot = float(stock_q.get("last") or 0.0)
        vwap = float(stock_q.get("vwap") or spot)
        is_call = "C" in occ_symbol[6:12] if len(occ_symbol) >= 12 else True

        # Calculate Active Confidence Score Checklist
        conf_score, conf_action, cl = calculate_active_trade_confidence(
            entry_price, bid, ask, spot, vwap, spy_change, qqq_change, is_call=is_call
        )

        pnl_dollar = round((bid - entry_price) * 100.0 * shares, 2)
        pnl_pct = ((bid - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

        stop_str = f"-${abs(stop_loss):.2f}" if stop_loss is not None else "NONE"
        target_str = f"+${profit_target:.2f}" if profit_target is not None else "NONE"

        print(f"\n📌 SYMBOL: {ticker} ({occ_symbol}) | Shares: {shares}x | Entry: ${entry_price:.2f} | Bid/Ask: ${bid:.2f}/${ask:.2f}")
        print(f" ├─ Realized Liquidation PnL: ${pnl_dollar:+.2f} ({pnl_pct:+.1f}%) | Bracket: [SL: {stop_str} / TP: {target_str}]")
        print(f" ├─ Composite Confidence Score: {conf_score} / 100.0 [{conf_action}]")
        print(f" ├─ Microstructure (25%): {cl['entry_microstructure']} | VWAP Align (25%): {cl['vwap_alignment']} | Beta (20%): {cl['beta_confluence']}")
        print(f" └─ Tape Velocity (15%): {cl['tape_acceleration']} | TOD Window (15%): {cl['time_of_day']}")

        # Check Triggers
        hit_tp = (profit_target is not None and pnl_dollar >= profit_target)
        hit_sl = (stop_loss is not None and pnl_dollar <= stop_loss)
        hit_conf_drop = (conf_action == "FORCE_SELL")

        if force_execution or hit_tp or hit_sl or hit_conf_drop or pnl_pct <= -20.0:
            trigger_label = "FORCE EXECUTION" if force_execution else ("TAKE PROFIT" if hit_tp else ("CONFIDENCE DROP (<50.0)" if hit_conf_drop else "STOP LOSS / PNL FLOOR"))
            print(f"[🚨 {trigger_label} EXECUTING CLOSE] Closing position {ticker} @ Bid ${bid:.2f}...")

            if force_execution or hit_conf_drop:
                force_close_position(occ_symbol, ticker, shares, bid, ask)
            else:
                if gex.execute_tradier_close_stepped(occ_symbol, ticker, shares, active_url):
                    fill_price = gex.get_recent_fill_price(occ_symbol, default_price=bid)
                    fill_score = calculate_fill_quality_score(fill_price, bid, ask, side="sell")
                    print(f"[✓ EXIT FILLED] {ticker} ({occ_symbol}) closed @ ${fill_price:.2f} | Fill Quality Score: {fill_score}/10.0")
                    try:
                        gex.synchronize_dynamo_with_tradier()
                    except Exception:
                        pass
        else:
            print(f"[🛡️ HOLDING] {ticker} Confidence ({conf_score}/100) & PnL (${pnl_dollar:+.2f}) are safely inside threshold limits.")

if __name__ == "__main__":
    global_target, ticker_brackets, target_env, force_execution = parse_args()

    if target_env.upper() == "PROD":
        print("🚨 [WARNING] TARGETING LIVE PRODUCTION ENVIRONMENT (6YB87601)")
        if os.path.exists('.env.prod'):
            load_dotenv('.env.prod', override=True)
        else:
            load_dotenv(override=True)
    else:
        print("🧪 [INFO] TARGETING SANDBOX ENVIRONMENT (VA83416608)")
        if os.path.exists('.env.sandbox'):
            load_dotenv('.env.sandbox', override=True)
        elif os.path.exists('.env'):
            load_dotenv('.env', override=True)

    scan_and_close_targets(global_target, ticker_brackets, force_execution)
