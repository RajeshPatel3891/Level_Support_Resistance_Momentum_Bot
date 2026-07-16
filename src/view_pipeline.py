import os
import sys
import argparse
import requests
from dotenv import load_dotenv

load_dotenv()

def get_headers():
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    return {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

def fetch_positions():
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    try:
        response = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=get_headers())
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and 'positions' in data:
                pos = data['positions'].get('position', [])
                return pos if isinstance(pos, list) else [pos]
        return []
    except Exception:
        return []

def get_live_quote(symbol):
    base_url = "https://sandbox.tradier.com/v1"
    try:
        response = requests.get(f"{base_url}/markets/quotes?symbols={symbol}", headers=get_headers())
        if response.status_code == 200:
            data = response.json()
            quote = data.get('quotes', {}).get('quote', {})
            if isinstance(quote, list): quote = quote[0]
            return quote
    except Exception:
        return {}
    return {}

def fetch_orders(statuses=None):
    account_id = os.getenv("TRADIER_ACCOUNT_ID")
    base_url = "https://sandbox.tradier.com/v1"
    params = {"limit": "150"}
    if statuses:
        params['status'] = ",".join(statuses)

    try:
        url = f"{base_url}/accounts/{account_id}/orders"
        r = requests.get(url, headers=get_headers(), params=params)
        if r.status_code == 200:
            orders_data = r.json().get('orders', {}) or {}
            orders_list = orders_data.get('order', []) if orders_data else []
            return orders_list if isinstance(orders_list, list) else [orders_list]
        return []
    except Exception:
        return []

def is_option_symbol(symbol):
    # OCC Option symbols are always longer than standard equity tickers (e.g., AAPL260717P00110000)
    return len(symbol) > 6

def calculate_realized_pnl(orders):
    """Matches filled buy and sell orders to calculate realized P&L."""
    fills = [o for o in orders if o.get('status') == 'filled']
    realized_summary = {}
    
    for o in fills:
        sym = o.get('option_symbol') or o.get('symbol', '')
        side = o.get('side', '').lower()
        qty = float(o.get('quantity', 0))
        price = float(o.get('avg_fill_price') or o.get('price') or 0.0)
        multiplier = 100.0 if is_option_symbol(sym) else 1.0
        
        if sym not in realized_summary:
            realized_summary[sym] = {"buys": [], "sells": []}
            
        if "buy" in side:
            realized_summary[sym]["buys"].append((qty, price, multiplier))
        elif "sell" in side:
            realized_summary[sym]["sells"].append((qty, price, multiplier))
            
    total_realized_pnl = 0.0
    matched_trades = []
    
    for sym, data in realized_summary.items():
        # Match FIFO / basic size allocation
        buy_qty = sum(q for q, _, _ in data["buys"])
        sell_qty = sum(q for q, _, _ in data["sells"])
        
        if buy_qty > 0 and sell_qty > 0:
            matched_qty = min(buy_qty, sell_qty)
            avg_buy = sum(q * p * m for q, p, m in data["buys"]) / buy_qty if buy_qty > 0 else 0
            avg_sell = sum(q * p * m for q, p, m in data["sells"]) / sell_qty if sell_qty > 0 else 0
            
            pnl = (avg_sell - avg_buy) * matched_qty
            total_realized_pnl += pnl
            matched_trades.append({
                "symbol": sym,
                "qty": matched_qty,
                "avg_buy": avg_buy / (100.0 if is_option_symbol(sym) else 1.0),
                "avg_sell": avg_sell / (100.0 if is_option_symbol(sym) else 1.0),
                "pnl": pnl
            })
            
    return matched_trades, total_realized_pnl

def display_dashboard(status_filters=None):
    print("=" * 105)
    print(f"🛰️  HARM.AI // UNIFIED ACTIVE PORTFOLIO & ORDER PIPELINE DASHBOARD")
    print("=" * 105)

    # 1. RENDER ACTIVE POSITIONS (P&L SECTION)
    print("\n📈 [SECTION 1] ACTIVE POSITION P&L (REAL-TIME)")
    print("-" * 105)
    positions = fetch_positions()
    
    if not positions:
        print("[📝] No active positions detected. Portfolio is currently flat.")
    else:
        print(f"{'Asset/Contract':<22} | {'Qty':<6} | {'Cost Basis':<12} | {'Last Price':<12} | {'Market Value':<14} | {'Unrealized P&L':<14}")
        print("-" * 105)
        for pos in positions:
            if not pos:
                continue
            symbol = pos.get('symbol', '')
            qty = float(pos.get('quantity', 0))
            cost_basis = float(pos.get('cost_basis', 0)) # Total position cost basis
            
            quote = get_live_quote(symbol)
            last_price = float(quote.get('last', 0.0))
            
            # Apply option contract multiplier rules
            multiplier = 100.0 if is_option_symbol(symbol) else 1.0
            
            # Recalculate true unit parameters
            unit_cost = cost_basis / (qty * multiplier) if qty > 0 else 0.0
            market_val = qty * multiplier * last_price
            pnl_val = market_val - cost_basis
            pnl_pct = (pnl_val / cost_basis) * 100 if cost_basis > 0 else 0.0
            
            print(f"{symbol:<22} | {qty:<6.1f} | ${cost_basis:<11,.2f} | ${last_price:<11,.2f} | ${market_val:<13,.2f} | {pnl_pct:+.2f}% (${pnl_val:+.2f})")
    print("-" * 105)

    # 2. RENDER HISTORICAL / PIPELINE ORDERS SECTION
    filter_label = status_filters or ["open", "filled", "rejected"]
    print(f"\n📋 [SECTION 2] RECENT PIPELINE ORDERS (FILTERED: {filter_label})")
    print("-" * 105)
    
    orders = fetch_orders(filter_label)
    if not orders:
        print("[📝] No matching orders found for current filter.")
    else:
        print(f"{'Order ID':<12} | {'Class':<6} | {'Symbol':<22} | {'Side':<13} | {'Qty':<5} | {'Price':<10} | {'Status':<12}")
        print("-" * 105)
        for o in reversed(orders[:30]):  # Show up to 30 most recent orders
            if not o:
                continue
            oid = o.get('id')
            oclass = o.get('class', '').upper()
            symbol = o.get('option_symbol') or o.get('symbol', '')
            side = o.get('side', '').upper()
            qty = float(o.get('quantity', 0))
            
            raw_price = o.get('avg_fill_price') or o.get('price')
            if raw_price is not None and float(raw_price) > 0:
                try:
                    price = f"${float(raw_price):,.2f}"
                except ValueError:
                    price = "MKT"
            else:
                price = "MKT"
                
            status = o.get('status', '').upper()
            print(f"{oid:<12} | {oclass:<6} | {symbol:<22} | {side:<13} | {qty:<5.1f} | {price:<10} | {status:<12}")
            
    print("-" * 105)

    # 3. CALCULATE REALIZED P&L ON FILLED ORDERS
    if "filled" in filter_label:
        print("\n💵 [SECTION 3] REALIZED CLOSED-TRADE P&L SUMMARY")
        print("-" * 105)
        all_filled_orders = fetch_orders(["filled"])
        matched_trades, total_pnl = calculate_realized_pnl(all_filled_orders)
        
        if not matched_trades:
            print("[📝] No fully closed matched cycles detected in recent order history.")
        else:
            print(f"{'Asset/Contract':<22} | {'Closed Qty':<10} | {'Avg Buy Price':<15} | {'Avg Sell Price':<15} | {'Realized P&L':<15}")
            print("-" * 105)
            for trade in matched_trades:
                print(f"{trade['symbol']:<22} | {trade['qty']:<10.1f} | ${trade['avg_buy']:<14.2f} | ${trade['avg_sell']:<14.2f} | {trade['pnl']:+.2f}")
            print("-" * 105)
            print(f"💰 Cumulative Realized P&L: {total_pnl:+.2f}")
            print("-" * 105)

    print(f"[⚙️] System synced. Awaiting level breakouts...")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HARM.AI Unified Dashboard")
    parser.add_argument("--status", type=str, help="Comma-separated statuses to filter order logs by (e.g. open,filled,rejected)")
    args = parser.parse_args()

    filter_list = [s.strip().lower() for s in args.status.split(",")] if args.status else ["open", "filled", "rejected"]
    display_dashboard(filter_list)
