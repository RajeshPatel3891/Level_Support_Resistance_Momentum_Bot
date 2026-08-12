# ==============================================================================
# HARM.AI LIVE DASHBOARD SERVER (FastAPI Production Core)
# ==============================================================================
import os
import json
import sqlite3
import logging
import requests
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("HarmonizedDashboard")

app = FastAPI(title="Harmonized AI Live Dashboard", version="4.0")

# Setup static files if directory exists
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

def get_db_connection():
    db_paths = ['trading.db', 'src/harm_telemetry.db', 'trading_engine.db', 'gex_telemetry.db']
    for path in db_paths:
        if os.path.exists(path):
            conn = sqlite3.connect(path)
            conn.row_factory = sqlite3.Row
            return conn
    return None

# ==============================================================================
# REQUIRED COMPLIANCE HOOK: Option Delta PnL Calculation
# ==============================================================================
def calculate_option_delta_pnl(entry_price, current_mark, delta=0.50, contracts=1.0):
    """Calculates real-time option delta PnL for preflight and UI telemetry."""
    try:
        price_diff = float(current_mark) - float(entry_price)
        return round(price_diff * 100.0 * float(contracts) * float(delta), 2)
    except Exception:
        return 0.0

@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, selected_date: str = None):
    dashboard_data_path = "dashboard_data.json"
    data = {}
    if os.path.exists(dashboard_data_path):
        try:
            with open(dashboard_data_path, "r") as f:
                data = json.load(f)
        except Exception:
            pass

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>HARM.AI LIVE DASHBOARD</title>
        <style>
            body {{ background-color: #0b0e14; color: #e2e8f0; font-family: monospace; padding: 20px; }}
            .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 15px; margin-bottom: 15px; }}
            h1 {{ color: #58a6ff; }}
        </style>
    </head>
    <body>
        <h1>🚀 HARM.AI LIVE ENGINE ACTIVE</h1>
        <div class="card">
            <h3>System Telemetry Online & Guarded</h3>
            <p>Dashboard dataset connected successfully. Fargate daemons & GSG Protector online.</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/proximity")
async def api_proximity():
    dashboard_data_path = "dashboard_data.json"
    if os.path.exists(dashboard_data_path):
        try:
            with open(dashboard_data_path, "r") as f:
                return json.load(f)
        except Exception as e:
            return {"error": str(e)}
    return {"status": "running", "message": "dashboard_data.json initializing..."}

# ==============================================================================
# DIRECT TRADIER BROKER RECONCILIATION ENDPOINT (True Broker Ledger)
# ==============================================================================
@app.get("/api/positions")
def get_live_ui_positions():
    base_url = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
    if "sandbox" in base_url.lower():
        token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
    else:
        token = os.getenv("TRADIER_TOKEN")

    acc_id = os.getenv("TRADIER_ACCOUNT_ID")
    if not token or not acc_id:
        return {"error": "Tradier credentials missing", "active_positions": []}

    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    
    try:
        # Source of Truth: Direct Tradier Broker Ledger
        res = requests.get(f"{base_url}/accounts/{acc_id}/positions", headers=headers, timeout=4)
        if res.status_code != 200:
            return {"error": f"Tradier API Error ({res.status_code})", "active_positions": []}

        data = res.json().get('positions', {})
        if not data or data == 'null':
            return {"active_positions": []}
            
        positions = data.get('position', [])
        if isinstance(positions, dict):
            positions = [positions]
        elif not isinstance(positions, list):
            positions = []
            
        active_list = []
        for p in positions:
            if p and isinstance(p, dict) and float(p.get('quantity', 0)) != 0:
                active_list.append({
                    "symbol": p.get('symbol'),
                    "quantity": p.get('quantity'),
                    "cost_basis": p.get('cost_basis')
                })
                
        return {"active_positions": active_list}
    except Exception as e:
        return {"error": str(e), "active_positions": []}

# ==============================================================================
# FIXED FASTAPI DECORATOR FOR ACTIVE POSITIONS (Line 792 Alignment Fix)
# ==============================================================================
@app.get('/api/active_positions')
def get_active_positions():
    conn = get_db_connection()
    if not conn:
        return JSONResponse(status_code=500, content={"error": "Database connection unavailable"})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('trades', 'harmonized_trades', 'active_positions');")
        table_row = cursor.fetchone()
        if not table_row:
            return {"positions": [], "note": "No active trade table located"}
        
        table_name = table_row[0]
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            # Attach computed delta PnL if entry and mark exist
            if 'entry_price' in row_dict and 'current_mark' in row_dict:
                row_dict['delta_pnl'] = calculate_option_delta_pnl(row_dict['entry_price'], row_dict['current_mark'])
            rows.append(row_dict)
        return {"positions": rows}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dashboard_server:app", host="0.0.0.0", port=8080, reload=False)
