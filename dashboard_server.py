import sqlite3
import os
import requests
import traceback
import pandas as pd
from datetime import datetime, date
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from jinja2 import Template
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="HARM.AI Mobile Matrix Gateway")

TRUE_BASIS = {
    "PLTR": 132.42, "INTC": 99.04, "AAPL": 324.86, "RIVN": 17.11,
    "TSLA": 391.84, "SOFI": 17.11, "NVDA": 209.34, "AAL": 15.18, "F": 14.05
}

INDEX_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HARM.AI LIVE</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-950 text-gray-100 font-sans p-4 max-w-lg mx-auto">

    <!-- Top Navigation with Calendar Selector & CSV Export -->
    <div class="flex items-center justify-between mb-4 bg-gray-900 p-3 rounded-xl border border-gray-800">
        <div class="flex items-center space-x-2">
            <span class="text-xl">🚀</span>
            <h1 class="text-xs font-bold tracking-wide text-red-500">HARM.AI LIVE</h1>
        </div>
        <div class="flex items-center space-x-2">
            <form action="/" method="GET" class="flex items-center">
                <input type="date" name="selected_date" value="{{ selected_date }}" 
                       onchange="this.form.submit()" 
                       class="bg-gray-800 text-xs text-white px-2 py-1 rounded border border-gray-700 focus:outline-none">
            </form>
            <a href="/export/trades?selected_date={{ selected_date }}" 
               class="bg-green-600 hover:bg-green-500 text-white text-xs px-2 py-1 rounded font-bold">
               CSV
            </a>
        </div>
    </div>

    <!-- PnL Header Cards -->
    <div class="grid grid-cols-2 gap-3 mb-6">
        <div class="bg-gray-900/80 p-3 rounded-xl border border-gray-800 text-center">
            <div class="text-[10px] text-gray-400 font-medium uppercase tracking-wider">FLOATING OPEN</div>
            <div class="text-xl font-black {{ pnl_class }}">{{ total_pnl }}</div>
        </div>
        <div class="bg-gray-900/80 p-3 rounded-xl border border-gray-800 text-center">
            <div class="text-[10px] text-gray-400 font-medium uppercase tracking-wider">REALIZED CLOSED</div>
            <div class="text-xl font-black {{ closed_pnl_class }}">{{ total_closed_pnl }}</div>
        </div>
    </div>

    <!-- Active Positions -->
    <h2 class="text-xs font-bold text-gray-400 uppercase mb-3 tracking-wider">ACTIVE POSITIONS</h2>
    <div class="space-y-3 mb-6">
        {% for trade in trades %}
        <div class="bg-gray-900/60 p-3 rounded-xl border border-gray-800 flex justify-between items-center">
            <div>
                <div class="flex items-center space-x-2">
                    <span class="font-black text-sm">{{ trade.ticker }}</span>
                    <span class="text-[10px] bg-gray-800 text-gray-300 px-1.5 py-0.5 rounded uppercase">{{ trade.status }}</span>
                </div>
                <div class="text-xs text-gray-400 mt-1">Live: <b class="text-gray-200">{{ trade.price }}</b> | Cost: <b class="text-gray-200">{{ trade.basis }}</b></div>
            </div>
            <div class="text-right">
                <div class="font-bold text-sm {{ trade.pnl_class }}">{{ trade.dollar_pnl }}</div>
                <div class="text-[10px] {{ trade.pnl_class }}">{{ trade.pnl_pct }}</div>
            </div>
        </div>
        {% endfor %}
    </div>

    <!-- Closed Positions -->
    <h2 class="text-xs font-bold text-gray-400 uppercase mb-3 tracking-wider">CLOSED POSITIONS ({{ selected_date }})</h2>
    <div class="space-y-3">
        {% for trade in closed_trades %}
        <div class="bg-gray-900/40 p-3 rounded-xl border border-gray-800/60 flex justify-between items-center">
            <div>
                <div class="flex items-center space-x-2">
                    <span class="font-bold text-xs text-gray-300">{{ trade.ticker }}</span>
                    <span class="text-[9px] bg-gray-800/80 text-gray-400 px-1 py-0.5 rounded">{{ trade.status }}</span>
                </div>
                <div class="text-[11px] text-gray-500 mt-0.5">Exit: {{ trade.exit_price }} | Cost: {{ trade.basis }}</div>
            </div>
            <div class="text-right">
                <div class="font-bold text-xs {{ trade.pnl_class }}">{{ trade.dollar_pnl }}</div>
                <div class="text-[9px] text-gray-500">{{ trade.timestamp }}</div>
            </div>
        </div>
        {% endfor %}
    </div>

</body>
</html>
"""

def get_db_connection():
    conn = sqlite3.connect("harm_telemetry.db")
    conn.row_factory = sqlite3.Row
    return conn

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

def fetch_portfolio_state(page: int = 1, selected_date: str = None):
    conn = get_db_connection()
    if not selected_date:
        latest_date_row = conn.execute("SELECT DATE(MAX(datetime(timestamp, '-4 hours'))) FROM trades").fetchone()
        selected_date = latest_date_row[0] if latest_date_row and latest_date_row[0] else date.today().strftime("%Y-%m-%d")

    active_trades = []
    closed_trades = []
    total_pnl = 0.0
    total_closed_pnl = 0.0
    
    limit = 50
    offset = (page - 1) * limit

    # Sum full realized closed PnL across all executed trades mapped to Eastern Time
    sum_row = conn.execute("""
        SELECT SUM(net_pnl) 
        FROM trades
        WHERE UPPER(exit_status) NOT IN ('ACTIVE', 'SIM_TRAILING_STOP')
          AND net_pnl IS NOT NULL
          AND DATE(datetime(timestamp, '-4 hours')) = ?
    """, (selected_date,)).fetchone()
    
    if sum_row and sum_row[0] is not None:
        total_closed_pnl = float(sum_row[0])

    # Fetch Active State
    db_active = conn.execute("""
        SELECT ticker, spot_price, stop_loss, take_profit, exit_status
        FROM trades 
        WHERE id IN (SELECT MAX(id) FROM trades GROUP BY ticker)
          AND UPPER(exit_status) = 'ACTIVE'
    """).fetchall()
    
    # Fetch Closed History List items for selected Eastern date
    db_closed = conn.execute("""
        SELECT ticker, spot_price, exit_price, exit_status, timestamp, net_pnl
        FROM trades
        WHERE UPPER(exit_status) NOT IN ('ACTIVE', 'SIM_TRAILING_STOP')
          AND net_pnl IS NOT NULL
          AND DATE(datetime(timestamp, '-4 hours')) = ?
        ORDER BY id DESC LIMIT ? OFFSET ?
    """, (selected_date, limit, offset)).fetchall()
    conn.close()
    
    for row in db_active:
        ticker = row[0]
        basis_val = TRUE_BASIS.get(ticker, float(row[1]) if row[1] else 1.0)
        sl = row[2]
        
        quote = get_live_quote(ticker)
        last_price = float(quote.get('last', 0)) if quote.get('last') else basis_val
        
        pnl_pct = ((last_price - basis_val) / basis_val) * 100 if basis_val > 0 else 0
        raw_risk_dist = abs(basis_val - (float(sl) if sl else 0.0))
        risk_dist = max(raw_risk_dist, 0.20)
        
        shares = min(85.0 / risk_dist, 500.0)
        dollar_pnl = (last_price - basis_val) * shares
        if sl and last_price <= float(sl):
            dollar_pnl = -85.00
            
        total_pnl += dollar_pnl
        active_trades.append({
            "ticker": ticker, "status": row[4], "price": f"${last_price:.2f}",
            "basis": f"${basis_val:.2f}", "pnl_pct": f"{pnl_pct:+.2f}%",
            "pnl_class": "text-green-400" if dollar_pnl >= 0 else "text-red-400", "dollar_pnl": f"${dollar_pnl:+.2f}"
        })
            
    for row in db_closed:
        ticker = row[0]
        basis_val = TRUE_BASIS.get(ticker, float(row[1]) if row[1] else 0.0)
        exit_val = float(row[2]) if row[2] else basis_val
        realized_pnl = float(row[5]) if row[5] is not None else 0.0

        closed_trades.append({
            "ticker": ticker, "status": row[3], "exit_price": f"${exit_val:.2f}",
            "basis": f"${basis_val:.2f}", "timestamp": str(row[4])[-8:],
            "pnl_class": "text-green-400" if realized_pnl >= 0 else "text-red-400", "dollar_pnl": f"${realized_pnl:+.2f}"
        })

    return active_trades, closed_trades, total_pnl, total_closed_pnl, selected_date

@app.get("/", response_class=HTMLResponse)
async def index_view(request: Request, selected_date: str = Query(default=None)):
    try:
        trades, closed, total_pnl, total_closed_pnl, current_date = fetch_portfolio_state(page=1, selected_date=selected_date)
        
        template = Template(INDEX_HTML_TEMPLATE)
        rendered_html = template.render(
            trades=trades, closed_trades=closed, selected_date=current_date,
            total_pnl=f"${total_pnl:+.2f}", pnl_class="text-green-400" if total_pnl >= 0 else "text-red-400",
            total_closed_pnl=f"${total_closed_pnl:+.2f}", closed_pnl_class="text-green-400" if total_closed_pnl >= 0 else "text-red-400"
        )
        return HTMLResponse(content=rendered_html)
    except Exception as e:
        return PlainTextResponse(f"DEBUG EXCEPTION:\n\n{traceback.format_exc()}", status_code=500)

@app.get("/export/trades")
async def export_trades_csv(selected_date: str = Query(default=None)):
    conn = get_db_connection()
    if not selected_date:
        latest_date_row = conn.execute("SELECT DATE(MAX(datetime(timestamp, '-4 hours'))) FROM trades").fetchone()
        selected_date = latest_date_row[0] if latest_date_row and latest_date_row[0] else date.today().strftime("%Y-%m-%d")

    query = "SELECT * FROM trades WHERE DATE(datetime(timestamp, '-4 hours')) = ? ORDER BY id DESC"
    df = pd.read_sql_query(query, conn, params=(selected_date,))
    conn.close()

    csv_data = df.to_csv(index=False)
    filename = f"Harmonized_Trades_{selected_date}.csv"

    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
