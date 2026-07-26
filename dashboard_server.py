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

    starting_cash = 3430.22
    unsettled_cash = 0.0
    try:
        ledger_row = conn.execute("SELECT starting_settled_cash, available_settled_cash, unsettled_cash FROM account_ledger WHERE date = ?", (selected_date,)).fetchone()
        if ledger_row:
            starting_cash = float(ledger_row[0]) if ledger_row[0] else 3430.22
            unsettled_cash = float(ledger_row[2]) if ledger_row[2] else 0.0
    except Exception:
        pass

    sum_row = conn.execute("""
        SELECT SUM(net_pnl) 
        FROM trades
        WHERE UPPER(exit_status) NOT IN ('ACTIVE', 'SIM_TRAILING_STOP')
          AND net_pnl IS NOT NULL
          AND DATE(datetime(timestamp, '-4 hours')) = ?
    """, (selected_date,)).fetchone()
    
    if sum_row and sum_row[0] is not None:
        total_closed_pnl = float(sum_row[0])

    db_active = conn.execute("""
        SELECT ticker, spot_price, stop_loss, take_profit, exit_status, entry_price, shares, direction
        FROM trades 
        WHERE id IN (SELECT MAX(id) FROM trades GROUP BY ticker)
          AND UPPER(exit_status) = 'ACTIVE'
    """).fetchall()
    
    db_closed = conn.execute("""
        SELECT ticker, spot_price, exit_price, exit_status, timestamp, net_pnl, entry_price, shares,
               strategy, stop_loss, take_profit, cso_cleared, cso_notes, direction
        FROM trades
        WHERE UPPER(exit_status) NOT IN ('ACTIVE', 'SIM_TRAILING_STOP')
          AND net_pnl IS NOT NULL
          AND DATE(datetime(timestamp, '-4 hours')) = ?
        ORDER BY id DESC LIMIT ? OFFSET ?
    """, (selected_date, limit, offset)).fetchall()
    conn.close()
    
    deployed_capital = 0.0

    for row in db_active:
        ticker = row['ticker']
        entry = float(row['entry_price']) if row['entry_price'] is not None else (float(row['spot_price']) if row['spot_price'] else 100.0)
        shares = float(row['shares']) if row['shares'] is not None else 1.0
        direction = row['direction'] if 'direction' in row.keys() else 'CALL'
        stored_spot = float(row['spot_price']) if row['spot_price'] is not None else 100.0
        stop_loss_val = float(row['stop_loss']) if row['stop_loss'] is not None else 0.0
        
        deployed_capital += (entry * shares)

        quote = get_live_quote(ticker)
        last_price = float(quote.get('last', stored_spot)) if quote.get('last') else stored_spot
        
        delta = 0.50
        spot_entry = stored_spot if stored_spot > 0 else last_price
        if str(direction).upper() == 'PUT':
            spot_diff = entry - last_price
        else:
            spot_diff = last_price - entry
        
        dollar_pnl = round(spot_diff * delta * 100 * shares, 2)
        pnl_pct = ((spot_diff * delta) / entry) * 100 if entry > 0 else 0.0
            
        total_pnl += dollar_pnl

        # Direction-aware GEX target resolution
        gex_target, stop_loss_val, gex_label = resolve_direction_targets(ticker, last_price, direction, stop_loss_val)

        target_label = f"GEX ({gex_label})"
        gex_target_str = f"${gex_target:,.2f} [{target_label}]" if gex_target else "Regime Active"
        
        gex_dist_val = "N/A"
        near_target = False
        hit_prob = 50.0
        tp_dollar = 0.0
        sl_dollar = 0.0
        rr_value = 1.0
        cso_eval = {"recommendation": "HOLD", "cso_badge_bg": "bg-gray-800", "cso_badge_text": "text-gray-300"}

        if gex_target and last_price > 0:
            diff_pct = ((last_price - gex_target) / last_price) * 100
            gex_dist_val = f"{diff_pct:+.2f}%"
            near_target = abs(diff_pct) <= 0.50

            hit_prob = calculate_gex_hit_probability(last_price, gex_target, gex_label)
            tp_dollar, sl_dollar = calculate_risk_return_dollars(last_price, gex_target, stop_loss_val, shares, delta)

            abs_tp = abs(tp_dollar)
            abs_sl = abs(sl_dollar) if abs(sl_dollar) > 0 else 1.0
            rr_value = round(abs_tp / abs_sl, 2)

            cso_eval = evaluate_cso_informed_exit(last_price, gex_target, stop_loss_val, hit_prob, dollar_pnl, shares, delta)

        if rr_value >= 1.50:
            rr_bg, rr_text, rr_border = "bg-emerald-950", "text-emerald-400", "border-emerald-800"
        elif rr_value >= 1.00:
            rr_bg, rr_text, rr_border = "bg-amber-950", "text-amber-400", "border-amber-800"
        else:
            rr_bg, rr_text, rr_border = "bg-red-950", "text-red-400", "border-red-800"

        active_trades.append({
            "ticker": ticker, "status": row['exit_status'], "price": f"${last_price:.2f}",
            "basis": f"${entry:.2f}", "pnl_pct": f"{pnl_pct:+.2f}%",
            "pnl_class": "text-green-400" if dollar_pnl >= 0 else "text-red-400", "dollar_pnl": f"${dollar_pnl:+.2f}",
            "gex_target_str": gex_target_str, "gex_dist": gex_dist_val, "near_target": near_target,
            "hit_probability": f"{hit_prob}%",
            "potential_tp_return": f"+${tp_dollar:,.2f}" if tp_dollar >= 0 else f"-${abs(tp_dollar):,.2f}",
            "potential_sl_risk": f"-${abs(sl_dollar):,.2f}",
            "rr_ratio": f"1:{rr_value:.2f}",
            "rr_bg": rr_bg, "rr_text": rr_text, "rr_border": rr_border,
            "cso_recommendation": cso_eval["recommendation"],
            "cso_badge_bg": cso_eval["cso_badge_bg"],
            "cso_badge_text": cso_eval["cso_badge_text"]
        })
            
    for row in db_closed:
        ticker = row['ticker'] if isinstance(row, sqlite3.Row) or hasattr(row, 'keys') else row[0]
        entry = float(row['entry_price']) if row['entry_price'] is not None else (float(row['spot_price']) if row['spot_price'] else 0.0)
        exit_val = float(row['exit_price']) if row['exit_price'] else entry
        realized_pnl = float(row['net_pnl']) if row['net_pnl'] is not None else 0.0
        
        sl_val = float(row['stop_loss']) if row['stop_loss'] is not None else 0.0
        tp_val = float(row['take_profit']) if row['take_profit'] is not None else 0.0
        strategy = row['strategy'] if row['strategy'] else "TACTICAL_FORCE"
        cso_notes = row['cso_notes'] if row['cso_notes'] else "None recorded"
        direction = row['direction'] if row['direction'] else "CALL"

        closed_trades.append({
            "ticker": ticker,
            "direction": direction,
            "status": row['exit_status'],
            "strategy": strategy,
            "exit_price": f"${exit_val:.2f}",
            "basis": f"${entry:.2f}",
            "stop_loss": f"${sl_val:.2f}",
            "take_profit": f"${tp_val:.2f}",
            "cso_notes": cso_notes,
            "timestamp": (datetime.strptime(str(row['timestamp']), "%Y-%m-%d %H:%M:%S") - timedelta(hours=4)).strftime("%m/%d %I:%M:%S %p EDT") if str(row['timestamp']) else "",
            "pnl_class": "text-green-400" if realized_pnl >= 0 else "text-red-400",
            "dollar_pnl": f"${realized_pnl:+.2f}"
        })

    effective_available = starting_cash + total_closed_pnl - deployed_capital

    ledger_data = {
        "starting_settled_cash": f"${starting_cash:,.2f}",
        "available_settled_cash": f"${effective_available:,.2f}",
        "deployed_capital": f"${deployed_capital:,.2f}",
        "unsettled_cash": f"${unsettled_cash:,.2f}"
    }

    return active_trades, closed_trades, total_pnl, total_closed_pnl, selected_date, ledger_data

@app.get("/", response_class=HTMLResponse)
async def index_view(request: Request, selected_date: str = Query(default=None)):
    try:
        trades, closed, total_pnl, total_closed_pnl, current_date, ledger = fetch_portfolio_state(page=1, selected_date=selected_date)
        
        template = Template(INDEX_HTML_TEMPLATE)
        rendered_html = template.render(
            trades=trades, closed_trades=closed, selected_date=current_date, ledger=ledger,
            total_pnl=f"${total_pnl:+.2f}", pnl_class="text-green-400" if total_pnl >= 0 else "text-red-400",
            total_closed_pnl=f"${total_closed_pnl:+.2f}", closed_pnl_class="text-green-400" if total_closed_pnl >= 0 else "text-red-400"
        )
        return HTMLResponse(content=rendered_html)
    except Exception as e:
        return PlainTextResponse(f"DEBUG EXCEPTION:\n\n{traceback.format_exc()}", status_code=500)

@app.post("/close-position/{ticker}")
async def close_position_action(ticker: str):
    try:
        conn = get_db_connection()
        row = conn.execute("SELECT entry_price, shares, spot_price FROM trades WHERE ticker = ? AND UPPER(exit_status) = 'ACTIVE'", (ticker.upper(),)).fetchone()
        
        if row:
            entry = float(row['entry_price']) if row['entry_price'] is not None else float(row['spot_price'])
            shares = float(row['shares']) if row['shares'] is not None else 1.0
            
            quote = get_live_quote(ticker)
            exit_price = float(quote.get('last', entry)) if quote.get('last') else entry
            
            spot_entry = float(row['spot_price']) if row['spot_price'] is not None else entry
            spot_diff = exit_price - spot_entry
            net_pnl = round(spot_diff * 0.50 * 100 * shares, 2)

            conn.execute("""
                UPDATE trades 
                SET exit_price = ?, exit_status = 'MANUAL_CLOSE', net_pnl = ?
                WHERE ticker = ? AND UPPER(exit_status) = 'ACTIVE'
            """, (exit_price, net_pnl, ticker.upper()))
            conn.commit()
        conn.close()
    except Exception as e:
        print(f"[!] Close Position Error ({ticker}): {e}")
    return RedirectResponse(url="/", status_code=303)

@app.post("/close-all")
async def close_all_positions_action():
    try:
        conn = get_db_connection()
        active_rows = conn.execute("SELECT ticker, entry_price, shares, spot_price FROM trades WHERE UPPER(exit_status) = 'ACTIVE'").fetchall()
        
        for row in active_rows:
            ticker = row['ticker']
            entry = float(row['entry_price']) if row['entry_price'] is not None else float(row['spot_price'])
            shares = float(row['shares']) if row['shares'] is not None else 1.0
            
            quote = get_live_quote(ticker)
            exit_price = float(quote.get('last', entry)) if quote.get('last') else entry
            
            spot_entry = float(row['spot_price']) if row['spot_price'] is not None else entry
            spot_diff = exit_price - spot_entry
            net_pnl = round(spot_diff * 0.50 * 100 * shares, 2)

            conn.execute("""
                UPDATE trades 
                SET exit_price = ?, exit_status = 'MANUAL_CLOSE', net_pnl = ?
                WHERE ticker = ? AND UPPER(exit_status) = 'ACTIVE'
            """, (exit_price, net_pnl, ticker))
          
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[!] Close All Error: {e}")
    return RedirectResponse(url="/", status_code=303)

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

@app.get('/api/proximity')
def get_proximity_data():
    try:
        with open('trading_levels.json', 'r') as f:
            levels = json.load(f)
    except Exception:
        return {}

    proximity = {}
    tickers = ["TSLA", "AAPL", "PLTR", "NVDA", "RIVN", "INTC", "SOFI", "AAL", "F"]

    for t in tickers:
        data = levels.get(t, {})
        if not data: continue
        
        spot = data.get('last_price', 0.0)
        vwap = data.get('vwap', 0.0)
        support_val = (data.get('support_a') or (data.get('support')[0] if isinstance(data.get('support'), list) and data.get('support') else data.get('support_b', 0.0)))
        sup_b = float(support_val) if support_val is not None else 0.0
        res_a = data.get('resistance_a', 0.0)
        
        dist_sup = round(abs(spot - sup_b), 2)
        dist_res = round(res_a - spot, 2) if spot < res_a else 0.0
        
        target_zone = "SUPPORT" if dist_sup <= dist_res else "RESISTANCE"
        gap = dist_sup if target_zone == "SUPPORT" else dist_res
        pct_gap = round((gap / spot) * 100, 2) if spot > 0 else 0.0

        proximity[t] = {
            "spot": spot,
            "vwap": vwap,
            "target": target_zone,
            "gap_dollars": f"${gap:.2f}",
            "gap_pct": f"{pct_gap:.2f}%",
            "armed": data.get("execution_armed", False)
        }

    return proximity

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8000)
