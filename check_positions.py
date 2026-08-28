import os
import requests

def check_account_status(env="SANDBOX"):
    if env.upper() == "PROD":
        token = "fyR75AACwlIYhkMyev1doRh6gnSr"
        acct = "6YB87601"
        base_url = "https://api.tradier.com/v1"
    else:
        token = "hcY1t0sY8RZmcsfVjQCA41ecAkFT"
        acct = "VA83416608"
        base_url = "https://sandbox.tradier.com/v1"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    # 1. Fetch Open Positions
    try:
        pos_res = requests.get(f"{base_url}/accounts/{acct}/positions", headers=headers).json()
        positions = pos_res.get("positions")
        if positions == "null" or not positions:
            positions = []
        else:
            positions = positions.get("position", [])
            if isinstance(positions, dict):
                positions = [positions]
    except Exception as e:
        positions = []
        print(f"[!] Error fetching positions: {e}")

    print("==================================================")
    print(f"📦 {env.upper()} ACTIVE POSITIONS & LIVE PNL ({acct})")
    print("==================================================")
    if positions:
        symbols = ",".join([p.get("symbol") for p in positions if p.get("symbol")])
        
        # Get live quotes for open positions
        quotes_dict = {}
        try:
            q_res = requests.get(f"{base_url}/markets/quotes", params={"symbols": symbols}, headers=headers).json()
            quotes = q_res.get("quotes", {}).get("quote", [])
            if isinstance(quotes, dict): quotes = [quotes]
            for q in quotes:
                quotes_dict[q.get("symbol")] = q.get("last", 0) or q.get("close", 0) or 0
        except Exception as e:
            print(f"[!] Error fetching quotes: {e}")

        for p in positions:
            sym = p.get("symbol")
            qty = float(p.get("quantity", 0))
            cost_basis = float(p.get("cost_basis", 0))
            last_price = quotes_dict.get(sym, 0)
            
            # Options multiplier is 100 per contract
            current_val = last_price * qty * 100 if last_price > 0 else cost_basis
            pnl = current_val - cost_basis
            pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
            
            pnl_str = f"+${pnl:.2f} (+{pnl_pct:.2f}%)" if pnl >= 0 else f"-${abs(pnl):.2f} ({pnl_pct:.2f}%)"
            
            print(f"Symbol: {sym}")
            print(f"  └─ Qty: {qty} | Cost Basis: ${cost_basis:.2f} | Last Price: ${last_price:.2f}")
            print(f"  └─ Current Val: ${current_val:.2f} | Live PnL: {pnl_str}\n")
    else:
        print(f"No open active positions found in {env.upper()}.")

    # 2. Fetch Today's Orders
    try:
        ord_res = requests.get(f"{base_url}/accounts/{acct}/orders", headers=headers).json()
        orders = ord_res.get("orders")
        if orders == "null" or not orders:
            orders = []
        else:
            orders = orders.get("order", [])
            if isinstance(orders, dict):
                orders = [orders]
    except Exception as e:
        orders = []
        print(f"[!] Error fetching orders: {e}")

    print("==================================================")
    print(f"📄 {env.upper()} TODAY'S ORDERS ({acct})")
    print("==================================================")
    if orders:
        for o in orders:
            print(f"ID: {o.get('id')} | Symbol: {o.get('symbol')} | Side: {o.get('side')} | Status: {o.get('status')} | Exec Price: ${o.get('avg_fill_price', 0)}")
    else:
        print(f"No order fills registered yet today in {env.upper()}.")

if __name__ == "__main__":
    import sys
    target_env = sys.argv[1] if len(sys.argv) > 1 else "SANDBOX"
    check_account_status(target_env)
