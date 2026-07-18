import sqlite3
import os
import json
import requests
import traceback
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="HARM.AI Mobile Matrix Gateway")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

def get_live_quote(symbol):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        r = requests.get(f"https://sandbox.tradier.com/v1/markets/quotes?symbols={symbol}", headers=headers)
        if r.status_code == 200:
            quote = r.json().get('quotes', {}).get('quote', {})
            return quote[0] if isinstance(quote, list) else quote
    except:
        return {}
    return {}

def fetch_portfolio_state():
    active_trades = []
    total_pnl = 0.0
    conn = sqlite3.connect("harm_telemetry.db")
    query = """
        SELECT ticker, spot_price, stop_loss, take_profit, exit_status, strategy
        FROM trades 
        WHERE id IN (SELECT MAX(id) FROM trades GROUP BY ticker)
    """
    db_records = conn.execute(query).fetchall()
    conn.close()
    
    for row in db_records:
        ticker, basis, sl, tp, status, strategy = row
        display_status = status if status else "ACTIVE"
        
        if display_status in ['ACTIVE', 'SIM_TRAILING_STOP']:
            quote = get_live_quote(ticker)
            last_price = float(quote.get('last', 0)) if quote.get('last') else (float(basis) if basis else 0.0)
            
            basis_val = float(basis) if basis else 1.0
            pnl_pct = ((last_price - basis_val) / basis_val) * 100 if basis_val > 0 else 0
            risk_dist = abs(basis_val - (float(sl) if sl else 0.0))
            
            if risk_dist > 0:
                shares = 85.0 / risk_dist
                dollar_pnl = (last_price - basis_val) * shares
                if sl and last_price <= float(sl):
                    dollar_pnl = -85.00
            else:
                dollar_pnl = 0.0
                
            total_pnl += dollar_pnl
            
            active_trades.append({
                "ticker": ticker,
                "status": display_status,
                "price": f"${last_price:.2f}",
                "basis": f"${basis_val:.2f}",
                "pnl_pct": f"{pnl_pct:+.2f}%",
                "pnl_class": "text-green-400" if dollar_pnl >= 0 else "text-red-400",
                "dollar_pnl": f"${dollar_pnl:+.2f}"
            })
            
    return active_trades, total_pnl

@app.get("/", response_class=HTMLResponse)
async def index_view(request: Request):
    try:
        trades, total_pnl = fetch_portfolio_state()
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "trades": trades, 
                "total_pnl": f"${total_pnl:+.2f}",
                "pnl_class": "text-green-400" if total_pnl >= 0 else "text-red-400"
            }
        )
    except Exception as e:
        error_msg = traceback.format_exc()
        return PlainTextResponse(f"DEBUG EXCEPTION IN ROOT VIEW:\n\n{error_msg}", status_code=500)

@app.get("/api/v1/matrix", response_class=HTMLResponse)
async def matrix_partial(request: Request):
    try:
        trades, total_pnl = fetch_portfolio_state()
        return templates.TemplateResponse(
            request=request,
            name="matrix_rows.html",
            context={
                "trades": trades, 
                "total_pnl": f"${total_pnl:+.2f}",
                "pnl_class": "text-green-400" if total_pnl >= 0 else "text-red-400"
            }
        )
    except Exception as e:
        error_msg = traceback.format_exc()
        return PlainTextResponse(f"DEBUG EXCEPTION IN PARTIAL VIEW:\n\n{error_msg}", status_code=500)
