from datetime import datetime, timedelta
import sys
import sqlite3
import os
import requests
import traceback
import json
import pandas as pd
from datetime import datetime, date
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse, RedirectResponse
from jinja2 import Template
from dotenv import load_dotenv

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from src.RiskEngine import (
    calculate_gex_hit_probability,
    calculate_risk_return_dollars,
    resolve_direction_targets,
    evaluate_cso_informed_exit
)

load_dotenv()

app = FastAPI(title="HARM.AI Mobile Matrix Gateway")

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

    <!-- Top Navigation -->
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
            {% if trades %}
            <form action="/close-all" method="POST" onsubmit="return confirm('⚠️ Close ALL active positions immediately?');">
                <button type="submit" class="bg-red-600 hover:bg-red-500 text-white text-xs px-2 py-1 rounded font-bold uppercase tracking-wider">
                    Close All
                </button>
            </form>
            {% endif %}
        </div>
    </div>

    <!-- Account Cash Ledger Banner -->
    <div class="grid grid-cols-4 gap-2 mb-4">
        <div class="bg-gray-900/80 p-2 rounded-xl border border-gray-800 text-center">
            <div class="text-[8px] text-gray-400 font-medium uppercase tracking-wider">STARTING</div>
            <div class="text-xs font-black text-gray-200">{{ ledger.starting_settled_cash }}</div>
        </div>
        <div class="bg-gray-900/80 p-2 rounded-xl border border-emerald-500/40 text-center">
            <div class="text-[8px] text-emerald-400 font-medium uppercase tracking-wider">SETTLED FREE</div>
            <div class="text-xs font-black text-emerald-400">{{ ledger.available_settled_cash }}</div>
        </div>
        <div class="bg-gray-900/80 p-2 rounded-xl border border-amber-500/40 text-center">
            <div class="text-[8px] text-amber-400 font-medium uppercase tracking-wider">DEPLOYED</div>
            <div class="text-xs font-black text-amber-400">{{ ledger.deployed_capital }}</div>
        </div>
        <div class="bg-gray-900/80 p-2 rounded-xl border border-gray-800 text-center">
            <div class="text-[8px] text-gray-400 font-medium uppercase tracking-wider">UNSETTLED</div>
            <div class="text-xs font-black text-gray-400">{{ ledger.unsettled_cash }}</div>
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
    <div class="flex items-center justify-between mb-3">
        <h2 class="text-xs font-bold text-gray-400 uppercase tracking-wider">ACTIVE POSITIONS, GEX TARGETS & RISK MATRIX</h2>
    </div>
    
    <div class="space-y-3 mb-6">
        {% for trade in trades %}
        <div class="bg-gray-900/60 p-3 rounded-xl border {% if trade.near_target %}border-emerald-500 shadow-lg shadow-emerald-950/50{% else %}border-gray-800{% endif %} flex justify-between items-center">
            <div class="space-y-1">
                <div class="flex items-center space-x-2">
                    <span class="font-black text-sm">{{ trade.ticker }}</span>
                    <span class="text-[10px] bg-gray-800 text-gray-300 px-1.5 py-0.5 rounded uppercase">{{ trade.status }}</span>
                    <span class="text-[9px] bg-purple-950 text-purple-300 border border-purple-800 px-1.5 py-0.5 rounded font-bold">
                        PROB: {{ trade.hit_probability }}
                    </span>
                    <span class="text-[9px] {{ trade.rr_bg }} {{ trade.rr_text }} {{ trade.rr_border }} border px-1.5 py-0.5 rounded font-bold">
                        R:R {{ trade.rr_ratio }}
                    </span>
                    <!-- CSO Dynamic Recommendation Badge -->
                    <span class="text-[9px] {{ trade.cso_badge_bg }} {{ trade.cso_badge_text }} px-1.5 py-0.5 rounded font-black tracking-wide">
                        CSO: {{ trade.cso_recommendation }}
                    </span>
                </div>
                
                <div class="text-xs text-gray-400">
                    Live: <b class="text-gray-200">{{ trade.price }}</b> | Cost: <b class="text-gray-200">{{ trade.basis }}</b>
                </div>

                <div class="text-[11px] text-purple-400">
                    GEX Target: <strong class="text-purple-300">{{ trade.gex_target_str }}</strong> (Dist: {{ trade.gex_dist }})
                </div>

                <!-- Explicit Dollar Risk & Return Overlay -->
                <div class="flex items-center space-x-3 text-[10px] pt-1 border-t border-gray-800/80">
                    <span class="text-emerald-400 font-bold">
                        🎯 TP Return: {{ trade.potential_tp_return }}
                    </span>
                    <span class="text-red-400 font-bold">
                        🛑 SL Risk: {{ trade.potential_sl_risk }}
                    </span>
                </div>
            </div>

            <div class="text-right flex items-center space-x-3">
                <div>
                    <div class="font-bold text-sm {{ trade.pnl_class }}">{{ trade.dollar_pnl }}</div>
                    <div class="text-[10px] {{ trade.pnl_class }}">{{ trade.pnl_pct }}</div>
                </div>
                <form action="/close-position/{{ trade.ticker }}" method="POST" onsubmit="return confirm('Close {{ trade.ticker }} position?');">
                    <button type="submit" class="bg-red-950/80 hover:bg-red-800 text-red-300 border border-red-800 text-[10px] px-2 py-1 rounded font-bold uppercase">
                        Close
                    </button>
                </form>
            </div>
        </div>
        {% endfor %}
    </div>

    <!-- LEVEL PROXIMITY MATRIX -->
    <div style="margin-top: 25px; margin-bottom: 25px;">
        <h3 style="color: #8f9bba; font-size: 14px; letter-spacing: 1px; margin-bottom: 12px; font-weight: 700;">LEVEL PROXIMITY MATRIX</h3>
        <div id="proximity-container" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px;"></div>
    </div>

    <script>
        async function fetchProximity() {
            try {
                const res = await fetch('/api/proximity');
                const data = await res.json();
                const container = document.getElementById('proximity-container');
                if (!container) return;
                
                let html = '';
                for (const [ticker, info] of Object.entries(data)) {
                    const statusBg = info.armed ? 'rgba(0, 230, 118, 0.15)' : 'rgba(255, 255, 255, 0.05)';
                    const statusColor = info.armed ? '#00e676' : '#8f9bba';
                    const statusText = info.armed ? 'ARMED' : 'WAITING';
                    
                    html += `
                        <div style="background: #111827; border: 1px solid #1f293d; border-radius: 8px; padding: 12px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                <span style="font-weight: 800; font-size: 16px; color: #ffffff;">${ticker}</span>
                                <span style="background: ${statusBg}; color: ${statusColor}; font-size: 10px; font-weight: 700; padding: 2px 8px; border-radius: 4px;">${statusText}</span>
                            </div>
                            <div style="font-size: 12px; color: #8f9bba; display: flex; justify-content: space-between; margin-bottom: 4px;">
                                <span>Spot: <strong style="color: #fff;">$${info.spot.toFixed(2)}</strong></span>
                                <span>VWAP: <strong style="color: #fff;">$${info.vwap.toFixed(2)}</strong></span>
                            </div>
                            <div style="font-size: 12px; color: #8f9bba; display: flex; justify-content: space-between;">
                                <span>Target: <strong style="color: #3b82f6;">${info.target}</strong></span>
                                <span>Gap: <strong style="color: #ffb74d;">${info.gap_dollars} (${info.gap_pct})</strong></span>
                            </div>
                        </div>
                    `;
                }
                container.innerHTML = html;
            } catch (e) {
                console.error("Proximity fetch error:", e);
            }
        }
        fetchProximity();
        setInterval(fetchProximity, 3000);
    </script>

    <!-- CLOSED POSITIONS WITH RICH TELEMETRY PANEL -->
    <h2 class="text-xs font-bold text-gray-400 uppercase mb-3 tracking-wider">CLOSED POSITIONS ({{ selected_date }})</h2>
    <div class="space-y-3">
        {% for trade in closed_trades %}
        <div class="bg-slate-900 border border-slate-800 rounded-lg p-3 mb-2 flex flex-col gap-2">
          <div class="flex justify-between items-center">
            <div class="flex items-center gap-2">
              <span class="font-bold text-white text-lg">{{ trade.ticker }}</span>
              <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">{{ trade.direction }}</span>
          <span class="text-xs px-2 py-0.5 rounded bg-amber-950 text-amber-400 font-mono border border-amber-800/80 font-bold">{{ trade.contracts }}x</span>
              <span class="text-xs px-2 py-0.5 rounded bg-blue-950 text-blue-400 font-mono border border-blue-800">{{ trade.status }}</span>
            </div>
            <div class="text-right">
              <span class="font-bold {{ trade.pnl_class }} text-lg">{{ trade.dollar_pnl }}</span>
              <div class="text-xs text-slate-400">{{ trade.timestamp }}</div>
            </div>
          </div>

          <!-- Rich Telemetry Sub-Panel -->
          <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs bg-slate-950 p-2 rounded border border-slate-800/60 font-mono">
            <div><span class="text-slate-500">Strategy:</span> <span class="text-slate-300">{{ trade.strategy }}</span></div>
            <div><span class="text-slate-500">Entry/Exit:</span> <span class="text-slate-300">{{ trade.basis }} / {{ trade.exit_price }}</span></div>
            <div><span class="text-slate-500">Stop Loss:</span> <span class="text-red-400">{{ trade.stop_loss }}</span></div>
            <div><span class="text-slate-500">Target:</span> <span class="text-emerald-400">{{ trade.take_profit }}</span></div>
          </div>

          <!-- CSO Reason Overlay -->
          <div class="text-xs bg-slate-950/80 px-2 py-1 rounded border border-slate-800/40 text-slate-400 font-mono flex items-center gap-1">
            <span class="text-amber-400 font-bold">📝 CSO Reason:</span> 
            <span class="text-slate-300">{{ trade.cso_notes }}</span>
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
    token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    if "sandbox" in base_url.lower():
        base_url = "https://sandbox.tradier.com/v1"
    try:
        r = requests.get(f"{base_url}/markets/quotes?symbols={symbol}", headers=headers, timeout=3)
        if r.status_code == 200:
            quote = r.json().get('quotes', {}).get('quote', {})
            return quote[0] if isinstance(quote, list) else quote
    except:
        return {}
    return {}

def fetch_portfolio_state(page=1, per_page=10, selected_date=None):
    import datetime
    import sqlite3
    conn = sqlite3.connect('harm_telemetry.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if selected_date:
        date_str = selected_date
    else:
        date_str = datetime.datetime.now().strftime('%Y-%m-%d')

    # 1. Starting Balance with Day-over-Day Rollover
    base_starting = 3430.22
    cursor.execute("SELECT COALESCE(SUM(net_pnl), 0.0) FROM trades WHERE exit_status != 'ACTIVE' AND DATE(timestamp) < DATE(?)", (date_str,))
    row = cursor.fetchone()
    prior_pnl = float(row[0]) if row and row[0] is not None else 0.0
    starting_balance = base_starting + prior_pnl

    # 2. Active Trades & Floating PnL
    cursor.execute("SELECT * FROM trades WHERE exit_status = 'ACTIVE'")
    active_trades = cursor.fetchall()
    floating_pnl = 0.0

    # 3. Closed Trades for selected date
    cursor.execute("SELECT * FROM trades WHERE exit_status != 'ACTIVE' AND DATE(timestamp) = DATE(?) ORDER BY id DESC", (date_str,))
    db_closed = cursor.fetchall()

    # 4. Realized Closed PnL
    cursor.execute("SELECT COALESCE(SUM(net_pnl), 0.0) FROM trades WHERE exit_status != 'ACTIVE' AND DATE(timestamp) = DATE(?)", (date_str,))
    row_closed = cursor.fetchone()
    total_closed_pnl = float(row_closed[0]) if row_closed and row_closed[0] is not None else 0.0

    # 5. Active Deployed Capital
    active_deployed = 0.0

    # 6. Settled Free
    settled_free = starting_balance + total_closed_pnl - active_deployed
    unsettled = 0.0

    conn.close()

    return active_trades, db_closed, floating_pnl, total_closed_pnl, date_str, starting_balance, settled_free, active_deployed, unsettled

@app.get("/", response_class=HTMLResponse)
async def index_view(request: Request, selected_date: str = Query(default=None)):
    trades, closed, total_pnl, total_closed_pnl, current_date, starting_balance, settled_free, deployed_capital, unsettled = fetch_portfolio_state(page=1, selected_date=selected_date)

    str_starting = f"${starting_balance:,.2f}"
    str_settled = f"${settled_free:,.2f}"
    str_deployed = f"${deployed_capital:,.2f}"
    str_unsettled = f"${unsettled:,.2f}"
    str_floating = f"${total_pnl:+.2f}"
    str_realized = f"${total_closed_pnl:+.2f}"

    ledger = {
        'starting_settled_cash': str_starting,
        'available_settled_cash': str_settled,
        'unsettled_cash': str_unsettled,
        'deployed_capital': str_deployed,
        'starting_balance': str_starting,
        'settled_free': str_settled,
        'floating_pnl': str_floating,
        'realized_pnl': str_realized
    }

    template = Template(INDEX_HTML_TEMPLATE)
    rendered_html = template.render(
        trades=trades,
        closed_trades=closed,
        selected_date=current_date,
        ledger=ledger,
        total_pnl=str_floating,
        pnl_class="text-green-400" if total_pnl >= 0 else "text-red-400",
        total_closed_pnl=str_realized,
        closed_pnl_class="text-green-400" if total_closed_pnl >= 0 else "text-red-400"
    )
    return HTMLResponse(content=rendered_html)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
