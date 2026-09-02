#!/usr/bin/env python3
import asyncio, os, time, sqlite3
from urllib.parse import parse_qs
from typing import Dict, List
from fastapi import FastAPI, Request
import uvicorn

app = FastAPI(title="HARM.AI Local Tradier Replay Gateway")

ACCOUNT_ID = "6YB87601"
current_quotes: Dict[str, dict] = {}
virtual_positions: Dict[str, dict] = {}
virtual_orders: Dict[str, dict] = {}

# Seed Equities (HOOD Spot: $21.50, VWAP: $21.75 - Bearish momentum favoring PUT)
current_quotes["HOOD"] = {"symbol": "HOOD", "last": 21.50, "vwap": 21.75, "change_percentage": -1.1}
current_quotes["SPY"] = {"symbol": "SPY", "last": 560.0, "change_percentage": -0.20}
current_quotes["QQQ"] = {"symbol": "QQQ", "last": 480.0, "change_percentage": -0.25}

# Seed HOOD Option Chain Quotes
# 1. Sub-$0.50 trap ($0.22 / $0.25) -> Gate 1 Rejection
current_quotes["HOOD260904P00020000"] = {"symbol": "HOOD260904P00020000", "bid": 0.22, "ask": 0.25, "last": 0.23, "open_interest": 400, "volume": 80}
# 2. Low-premium maker target ($0.54 / $0.56, Mid $0.55 <= 0.60) -> Passive Maker Bid
current_quotes["HOOD260904P00021000"] = {"symbol": "HOOD260904P00021000", "bid": 0.54, "ask": 0.56, "last": 0.55, "open_interest": 1200, "volume": 650}
# 3. High-delta contract ($0.88 / $0.91, Mid $0.895 > 0.60) -> Midpoint Walker
current_quotes["HOOD260904P00022000"] = {"symbol": "HOOD260904P00022000", "bid": 0.88, "ask": 0.91, "last": 0.89, "open_interest": 2500, "volume": 1800}

@app.get("/v1/markets/quotes")
async def get_quotes(symbols: str):
    res = []
    for s in [sym.strip() for sym in symbols.split(",")]:
        res.append(current_quotes.get(s, {"symbol": s, "bid": 0.50, "ask": 0.52, "last": 0.51, "vwap": 0.51}))
    return {"quotes": {"quote": res[0] if len(res) == 1 else res}}

@app.get("/v1/markets/options/expirations")
async def get_expirations(symbol: str):
    return {"expirations": {"date": ["2026-09-04", "2026-09-11"]}}

@app.get("/v1/markets/options/chains")
async def get_option_chains(symbol: str, expiration: str):
    s = symbol.upper()
    if s == "HOOD":
        opts = [
            {"symbol": "HOOD260904P00020000", "option_type": "put", "strike": 20.0, "bid": 0.22, "ask": 0.25, "open_interest": 400, "volume": 80},
            {"symbol": "HOOD260904P00021000", "option_type": "put", "strike": 21.0, "bid": 0.54, "ask": 0.56, "open_interest": 1200, "volume": 650},
            {"symbol": "HOOD260904P00022000", "option_type": "put", "strike": 22.0, "bid": 0.88, "ask": 0.91, "open_interest": 2500, "volume": 1800}
        ]
    else:
        opts = [
            {"symbol": f"{s}260904P00050000", "option_type": "put", "strike": 50.0, "bid": 0.54, "ask": 0.56, "open_interest": 500, "volume": 200}
        ]
    return {"options": {"option": opts}}

@app.get(f"/v1/accounts/{ACCOUNT_ID}/positions")
async def get_positions():
    pos = list(virtual_positions.values())
    if not pos:
        return {"positions": "null"}
    return {"positions": {"position": pos}}

@app.post(f"/v1/accounts/{ACCOUNT_ID}/orders")
async def place_order(request: Request):
    raw_body = await request.body()
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        import json
        data = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    else:
        parsed = parse_qs(raw_body.decode("utf-8"))
        data = {k: v[0] for k, v in parsed.items()}

    order_id = str(int(time.time() * 1000))
    limit_p = float(data.get("price", 0.0) or 0.0)
    occ = data.get("option_symbol", data.get("symbol", "HOOD260904P00021000"))
    qty = int(float(data.get("quantity", 1) or 1))
    side = data.get("side", "buy_to_open")

    virtual_orders[order_id] = {
        "id": order_id,
        "symbol": occ,
        "side": side,
        "price": limit_p,
        "quantity": qty,
        "status": "open",
        "created_at": time.time()
    }
    print(f"\n[📋 MOCK GATEWAY] Received {side} {qty}x {occ} @ ${limit_p:.2f} (ID: {order_id})")
    return {"order": {"id": order_id, "status": "ok"}}

@app.get(f"/v1/accounts/{ACCOUNT_ID}/orders/{{order_id}}")
async def get_order_status(order_id: str):
    ord_info = virtual_orders.get(order_id, {"status": "rejected"})
    if ord_info.get("status") == "open" and (time.time() - ord_info.get("created_at", 0)) >= 2.0:
        ord_info["status"] = "filled"
        ord_info["avg_fill_price"] = ord_info["price"]
        ord_info["exec_quantity"] = ord_info["quantity"]
        virtual_positions[ord_info["symbol"]] = {
            "id": 201,
            "symbol": "HOOD",
            "option_symbol": ord_info["symbol"],
            "quantity": ord_info["quantity"],
            "cost_basis": ord_info["price"] * 100 * ord_info["quantity"],
            "date_acquired": "2026-09-01T20:00:00.000Z"
        }
        print(f"[✅ MOCK FILL COMPLETED] {ord_info['quantity']}x {ord_info['symbol']} filled @ ${ord_info['price']:.2f}")
    return {"order": ord_info}

@app.delete(f"/v1/accounts/{ACCOUNT_ID}/orders/{{order_id}}")
async def cancel_order(order_id: str):
    if order_id in virtual_orders:
        virtual_orders[order_id]["status"] = "canceled"
        print(f"[🚫 MOCK CANCEL] Order {order_id} canceled.")
    return {"order": {"id": order_id, "status": "canceled"}}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
