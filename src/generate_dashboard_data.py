import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.getcwd())
import os
import re
import json
import time
import requests
import sqlite3
import boto3
from boto3.dynamodb.conditions import Attr
from check_and_close_target import calculate_active_trade_confidence, calculate_fill_quality_score

DB_PATH = "harm_telemetry.db"
OUTPUT_PATH = "dashboard_data.json"

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

def generate_data():
    env = os.getenv("EXECUTION_ENV", "SANDBOX").upper()
    table_name = os.getenv("DYNAMODB_TABLE", "HarmonizedTrades_Sandbox" if env == "SANDBOX" else "HarmonizedTrades")
    tenant_id = os.getenv("TENANT_ID", "COMPANY_A_SANDBOX" if env == "SANDBOX" else "COMPANY_A_PROD")
    region = os.getenv("AWS_REGION", "us-east-1")

    base_url = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1" if env == "SANDBOX" else "https://api.tradier.com/v1").rstrip("/")
    token = os.getenv("TRADIER_SANDBOX_TOKEN" if env == "SANDBOX" else "TRADIER_TOKEN")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    # --- 1. Fetch Balances (Legacy Support) ---
    equity = 100000.0
    try:
        account_id = os.getenv("TRADIER_ACCOUNT_ID", "VA83416608")
        res = requests.get(f"{base_url}/accounts/{account_id}/balances", headers=headers, timeout=5)
        if res.status_code == 200:
            b = res.json().get("balances", {})
            equity = float(b.get("total_equity") or 100000.0)
    except Exception as e:
        print(f"[!] Tradier balance fetch error: {e}")

    # --- 2. Fetch Closed Trades from SQLite (Legacy Support) ---
    closed_trades = []
    total_realized_pnl = 0.0
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
            if cursor.fetchone():
                cursor.execute("SELECT * FROM trades ORDER BY rowid DESC")
                rows = cursor.fetchall()
                for row in rows:
                    d = dict(row)
                    status = str(d.get("exit_status", "ACTIVE")).upper()
                    if status != "ACTIVE":
                        entry = float(d.get("entry_price", d.get("spot_price", 0.0) or 0.0))
                        exit_px = float(d.get("exit_price", 0.0) or 0.0)
                        shares = int(d.get("shares", 1) or 1)
                        pnl = 0.0
                        if exit_px > 0:
                            pnl = round((exit_px - entry) * shares * 100, 2)
                            total_realized_pnl += pnl

                        sl = d.get("stop_loss")
                        tp = d.get("take_profit")
                        reason = d.get("cso_reason") or d.get("strategy") or "SMART_CSO_LIVE"

                        trade_obj = {
                            "id": d.get("id"),
                            "ticker": d.get("ticker"),
                            "direction": d.get("direction"),
                            "strategy": d.get("strategy", "SMART_CSO_LIVE"),
                            "entry_price": entry,
                            "exit_price": exit_px,
                            "stop_loss": f"${float(sl):.2f}" if sl else f"${entry * 0.80:.2f}",
                            "take_profit": f"${float(tp):.2f}" if tp else f"${entry * 1.50:.2f}",
                            "target": f"${float(tp):.2f}" if tp else f"${entry * 1.50:.2f}",
                            "cso_reason": reason,
                            "exit_status": status,
                            "timestamp": d.get("timestamp"),
                            "occ_symbol": d.get("occ_symbol", ""),
                            "realized_pnl": pnl
                        }
                        closed_trades.append(trade_obj)
            conn.close()
        except Exception as e:
            print(f"[-] SQLite Read Error: {e}")

    # --- 3. Fetch Active Positions from DynamoDB ---
    raw_items = []
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table(table_name)
        res = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE') & Attr('tenant_id').eq(tenant_id))
        raw_items = res.get('Items', [])
    except Exception as e:
        print(f"[-] DynamoDB Scan Error: {e}")

    # --- 4. Fetch GEX Trading Levels Context ---
    gex_levels = {}
    if os.path.exists("trading_levels.json"):
        try:
            with open("trading_levels.json", "r") as f:
                data = json.load(f)
                gex_levels = data.get("levels", data) if isinstance(data, dict) else {}
        except Exception:
            pass

    # --- 5. Batch Quote Enriched Telemetry Calculation ---
    active_cards = []
    if raw_items:
        symbols = [item.get("occ_symbol", item.get("ticker")) for item in raw_items]
        underlying_symbols = list(set([item.get("ticker") for item in raw_items]))
        query_str = ",".join(list(set(symbols + underlying_symbols + ["SPY", "QQQ"])))

        quotes_dict = {}
        try:
            q_res = requests.get(f"{base_url}/markets/quotes", headers=headers, params={"symbols": query_str}, timeout=3.0)
            if q_res.status_code == 200:
                quotes = q_res.json().get("quotes", {}).get("quote", [])
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
        except Exception as e:
            print(f"[-] Quote Fetch Warning: {e}")

        spy_change = quotes_dict.get("SPY", {}).get("change_pct", 0.0)
        qqq_change = quotes_dict.get("QQQ", {}).get("change_pct", 0.0)

        for item in raw_items:
            ticker = item.get("ticker")
            occ_symbol = item.get("occ_symbol", ticker)
            direction = item.get("direction", "CALL")
            entry_price = float(item.get("entry_price", 0.0))
            shares = float(item.get("shares", 1.0))

            opt_quote = quotes_dict.get(occ_symbol, {})
            opt_bid = float(opt_quote.get("bid", entry_price))
            opt_ask = float(opt_quote.get("ask", entry_price))

            stock_quote = quotes_dict.get(ticker, {})
            spot_price = float(stock_quote.get("last", float(item.get("spot_price", 0.0))))
            vwap = float(stock_quote.get("vwap", spot_price))

            # Metric Calculations
            conf_score, conf_action, _ = calculate_active_trade_confidence(
                entry_price, opt_bid, opt_ask, spot_price, vwap, spy_change, qqq_change, is_call=(direction == "CALL")
            )
            fill_score = calculate_fill_quality_score(entry_price, opt_bid, opt_ask, side="buy")
            gex_status = check_gex_engagement(ticker, direction, spot_price, gex_levels)

            current_val = opt_bid * shares * 100.0
            cost_basis = entry_price * shares * 100.0
            pnl_dollars = current_val - cost_basis
            pnl_pct = (pnl_dollars / cost_basis * 100.0) if cost_basis > 0 else 0.0

            sl_val = float(item.get("stop_loss", entry_price * 0.8))
            tp_val = float(item.get("take_profit", entry_price * 1.5))

            card = {
                "trade_id": item.get("trade_id") or item.get("id"),
                "id": item.get("trade_id") or item.get("id"), 
                "ticker": ticker,
                "occ_symbol": occ_symbol,
                "direction": direction,
                "strategy": item.get("strategy", "SMART_CSO_LIVE"),
                "shares": shares,
                "entry_price": entry_price,
                "current_bid": opt_bid,
                "current_ask": opt_ask,
                "spot_price": spot_price,
                "vwap": vwap,
                "pnl_dollars": round(pnl_dollars, 2),
                "pnl_pct": round(pnl_pct, 2),
                "realized_pnl": round(pnl_dollars, 2),
                "fill_quality_score": round(fill_score, 1),
                "confidence_score": round(conf_score, 0),
                "confidence_status": "🟢 HIGH" if conf_score >= 80 else ("🟡 MED" if conf_score >= 50 else "🔴 LOW"),
                "gex_engagement": gex_status,
                "stop_loss": f"${sl_val:.2f}",
                "take_profit": f"${tp_val:.2f}",
                "target": f"${tp_val:.2f}",
                "exit_status": "ACTIVE",
                "timestamp": item.get("timestamp")
            }
            active_cards.append(card)

    # --- 6. Compile Hybrid Payload ---
    payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S ET"),
        "environment": env,
        "summary": {"total_value": equity, "realized_pnl": round(total_realized_pnl, 2)},
        "total_value": equity,
        "starting_cash": equity,
        "total_equity": equity,
        "active_positions": [],
        "level_matrix": [],
        "active_trades": active_cards,       # Populates legacy UI components
        "active_trade_cards": active_cards,  # Target for new rich telemetry UI
        "closed_trades": closed_trades,
        "total_realized_closed": round(total_realized_pnl, 2)
    }

    with open(OUTPUT_PATH, "w") as f:
        json.dump(payload, f, indent=2)

    print(f"[✓] Re-compiled {len(active_cards)} active, {len(closed_trades)} closed. Realized PnL: ${total_realized_pnl:.2f}")
    return payload

if __name__ == "__main__":
    generate_data()
