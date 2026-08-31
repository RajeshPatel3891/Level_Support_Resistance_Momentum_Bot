import os
from dotenv import load_dotenv
exec_env_passed = os.getenv("EXECUTION_ENV", "").upper()
if not exec_env_passed and os.path.exists(".env.prod"):
    load_dotenv(".env.prod", override=False)

import os
import sys
import json
import sqlite3
import requests
import tempfile
import traceback
import subprocess
import uvicorn
import pandas as pd
from datetime import datetime, date, timedelta
from fastapi import FastAPI, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse, RedirectResponse, JSONResponse
from jinja2 import Template
import boto3
from boto3.dynamodb.conditions import Attr

EXEC_ENV = os.getenv("EXECUTION_ENV", "SANDBOX").upper()

if EXEC_ENV in ["PROD", "PRODUCTION", "LIVE"]:
    if os.path.exists(".env.prod"):
        load_dotenv(".env.prod", override=True)
    else:
        load_dotenv(override=True)
else:
    if os.path.exists(".env.sandbox"):
        load_dotenv(".env.sandbox", override=True)
    else:
        load_dotenv(override=True)

CURRENT_ENV = os.getenv("EXECUTION_ENV", EXEC_ENV).upper()
TARGET_IS_LIVE = 1 if CURRENT_ENV in ["PROD", "PRODUCTION", "LIVE"] else 0
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'harm_telemetry.db')

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

from src.RiskEngine import (
    calculate_gex_hit_probability,
    calculate_risk_return_dollars,
    resolve_direction_targets,
    evaluate_cso_informed_exit
)

def get_dynamic_proximity_threshold(price: float) -> float:
    if price >= 100.0:
        return 0.0075
    elif price >= 30.0:
        return 0.0085
    else:
        return 0.0120

def resolve_trade_direction(item):
    raw_dir = str(item.get('direction') or '').strip().upper()
    if raw_dir and raw_dir != '-':
        return raw_dir
    occ = str(item.get('occ_symbol') or '').upper()
    ticker = str(item.get('ticker') or '').upper()
    if occ and ticker and len(occ) > len(ticker):
        suffix = occ[len(ticker):]
        if 'C' in suffix[:7]:
            return 'CALL'
        elif 'P' in suffix[:7]:
            return 'PUT'
    return 'CALL'

def init_cloud_state_and_hydrate():
    aws_region = os.getenv("AWS_REGION", "us-east-1")
    dynamo_table_name = os.getenv("DYNAMO_TABLE_NAME", "HarmonizedTrades")
    dynamodb = boto3.resource('dynamodb', region_name=aws_region)
    try:
        table = dynamodb.Table(dynamo_table_name)
        table.load()
    except Exception:
        table = dynamodb.create_table(
            TableName=dynamo_table_name,
            KeySchema=[{'AttributeName': 'ticker', 'KeyType': 'HASH'}],
            AttributeDefinitions=[{'AttributeName': 'ticker', 'AttributeType': 'S'}],
            BillingMode='PAY_PER_REQUEST'
        )
        table.wait_until_exists()

    db_path = "/app/harm_telemetry.db" if os.path.exists("/app/harm_telemetry.db") else DB_PATH
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            ticker TEXT PRIMARY KEY, timestamp TEXT, strategy TEXT, direction TEXT,
            spot_price REAL, entry_price REAL, shares REAL, stop_loss REAL,
            take_profit REAL, net_pnl REAL, exit_status TEXT, is_live INTEGER,
            occ_symbol TEXT, execution_env TEXT, unrealized_pnl REAL, option_mark REAL, gsg_status TEXT
        )
    """)
    conn.commit()

    try:
        response = table.scan(
            FilterExpression="exit_status = :status",
            ExpressionAttributeValues={":status": "ACTIVE"}
        )
        items = response.get('Items', [])
        for item in items:
            c.execute("""
                INSERT OR REPLACE INTO trades 
                (ticker, timestamp, strategy, direction, spot_price, entry_price, shares, stop_loss, take_profit, net_pnl, exit_status, is_live, occ_symbol, execution_env)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get('ticker'), item.get('timestamp'), item.get('strategy'), item.get('direction'),
                float(item.get('spot_price', 0)), float(item.get('entry_price', 0)), float(item.get('shares', 0)),
                float(item.get('stop_loss', 0)), float(item.get('take_profit', 0)), float(item.get('net_pnl', 0)),
                item.get('exit_status', 'ACTIVE'), int(item.get('is_live', 1)), item.get('occ_symbol', ''),
                item.get('execution_env', 'SANDBOX')
            ))
        conn.commit()
    except Exception as e:
        pass
    finally:
        conn.close()

try:
    init_cloud_state_and_hydrate()
except Exception as e:
    pass

def fetch_closed_dynamo_positions(selected_date=None):
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        filter_expr = Attr('exit_status').ne('ACTIVE') & (
            Attr('execution_env').eq(CURRENT_ENV) | Attr('is_live').eq(TARGET_IS_LIVE)
        )
        res = table.scan(FilterExpression=filter_expr)
        raw_items = res.get('Items', [])
        parsed = []
        for item in raw_items:
            try:
                ts = str(item.get('exit_timestamp', item.get('timestamp', '')))
                if selected_date and not ts.startswith(selected_date):
                    continue
                parsed.append({
                    'trade_id': str(item.get('trade_id')),
                    'ticker': str(item.get('ticker')),
                    'timestamp': ts,
                    'strategy': str(item.get('strategy', 'BREAKOUT')),
                    'direction': resolve_trade_direction(item),
                    'entry_price': float(item.get('entry_price', 0.0)),
                    'exit_price': float(item.get('exit_price', 0.0)),
                    'exit_status': str(item.get('exit_status', 'CLOSED')),
                    'net_pnl': float(item.get('net_pnl', 0.0)),
                    'shares': abs(float(item.get('shares', 1.0)))
                })
            except Exception:
                continue
        return parsed
    except Exception as e:
        return []

def fetch_all_active_dynamo_positions():
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        filter_expr = Attr('exit_status').eq('ACTIVE') & (
            Attr('execution_env').eq(CURRENT_ENV) | Attr('is_live').eq(TARGET_IS_LIVE)
        )
        res = table.scan(FilterExpression=filter_expr)
        raw_items = res.get('Items', [])
        parsed = []
        for item in raw_items:
            try:
                shares = float(item.get('shares', 1.0))
                if shares <= 0:
                    continue
                entry_price = float(item.get('entry_price', 0.0))
                parsed.append({
                    'trade_id': str(item.get('trade_id')),
                    'ticker': str(item.get('ticker')),
                    'timestamp': str(item.get('timestamp', '')),
                    'strategy': str(item.get('strategy', 'BREAKOUT')),
                    'direction': resolve_trade_direction(item),
                    'spot_price': float(item.get('spot_price', entry_price)),
                    'entry_price': entry_price,
                    'shares': abs(shares),
                    'stop_loss': float(item.get('stop_loss', round(entry_price * 0.80, 2))),
                    'take_profit': float(item.get('take_profit', round(entry_price * 1.50, 2))),
                    'net_pnl': float(item.get('net_pnl', 0.0)),
                    'exit_status': 'ACTIVE',
                    'is_live': int(item.get('is_live', TARGET_IS_LIVE)),
                    'occ_symbol': str(item.get('occ_symbol', item.get('ticker'))),
                    'cso_notes': item.get('cso_notes') or item.get('cso_reason'),
                    'cso_recommendation': item.get('cso_recommendation') or item.get('cso_status')
                })
            except Exception:
                continue
        return parsed
    except Exception as e:
        return []

app = FastAPI(title="HARM.AI Live Dashboard Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INDEX_HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HARM.AI LIVE</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-950 text-gray-100 font-sans p-4 max-w-7xl mx-auto">

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

    <!-- MAIN TWO-COLUMN DASHBOARD GRID -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">

        <!-- LEFT COLUMN: Portfolio Ledger, Controls, & Trades (7 Cols) -->
        <div class="lg:col-span-7 space-y-6">

            <!-- Account Cash Ledger Banner -->
            <div class="grid grid-cols-4 gap-2">
                <div class="bg-gray-900/80 p-2 rounded-xl border border-gray-800 text-center">
                    <div class="text-[8px] text-gray-400 font-medium uppercase tracking-wider">STARTING</div>
                    <div class="text-xs font-black text-gray-200">{{ str_starting }}</div>
                </div>
                <div class="bg-gray-900/80 p-2 rounded-xl border border-emerald-500/40 text-center">
                    <div class="text-[8px] text-emerald-400 font-medium uppercase tracking-wider">SETTLED FREE</div>
                    <div class="text-xs font-black text-emerald-400">{{ str_settled }}</div>
                </div>
                <div class="bg-gray-900/80 p-2 rounded-xl border border-amber-500/40 text-center">
                    <div class="text-[8px] text-amber-400 font-medium uppercase tracking-wider">DEPLOYED</div>
                    <div class="text-xs font-black text-amber-400">{{ str_deployed }}</div>
                </div>
                <div class="bg-gray-900/80 p-2 rounded-xl border border-gray-800 text-center">
                    <div class="text-[8px] text-gray-400 font-medium uppercase tracking-wider">UNSETTLED</div>
                    <div class="text-xs font-black text-gray-400">{{ str_unsettled }}</div>
                </div>
            </div>

            <!-- PnL Header Cards -->
            <div class="grid grid-cols-2 gap-3">
                <div class="bg-gray-900/80 p-3 rounded-xl border border-gray-800 text-center">
                    <div class="text-[10px] text-gray-400 font-medium uppercase tracking-wider">FLOATING OPEN</div>
                    <div class="text-xl font-black {{ pnl_class }}">{{ total_pnl }}</div>
                </div>
                <div class="bg-gray-900/80 p-3 rounded-xl border border-gray-800 text-center">
                    <div class="text-[10px] text-gray-400 font-medium uppercase tracking-wider">REALIZED CLOSED</div>
                    <div class="text-xl font-black {{ closed_pnl_class }}">{{ total_closed_pnl }}</div>
                </div>
            </div>

            <!-- STRATEGY CONFIGURATION & GUARDS PANEL -->
            <div class="bg-gray-900/90 border border-amber-500/30 rounded-xl p-4 shadow-xl">
                <div class="flex items-center justify-between pb-3 mb-3 border-b border-gray-800">
                    <div>
                        <h2 class="text-xs font-bold text-blue-400 tracking-wider uppercase flex items-center gap-1">
                            ⚙️ STRATEGY CONFIGURATION & GUARDS
                        </h2>
                        <p class="text-[9px] text-gray-400 font-mono mt-0.5">DYNAMIC ORDER PARAMETER ENFORCEMENT ENGINE</p>
                    </div>
                    <div class="flex items-center space-x-2">
                        <button type="button" onclick="triggerConfigAudit()" class="bg-blue-600 hover:bg-blue-500 text-white font-bold text-[10px] px-2.5 py-1 rounded shadow cursor-pointer">⚡ AUDIT</button>
                        <button type="button" onclick="triggerAutoScout()" class="bg-amber-600 hover:bg-amber-500 text-white font-bold text-[10px] px-2.5 py-1 rounded shadow cursor-pointer">🚀 AUTO-SCOUT</button>
                        <button type="button" onclick="saveStrategyConfig()" class="bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-[10px] px-2.5 py-1 rounded shadow cursor-pointer">SAVE CHANGES</button>
                        <button type="button" onclick="toggleConfigBody()" id="btn-toggle-config" class="bg-gray-800 hover:bg-gray-700 text-gray-300 text-[10px] px-2 py-1 rounded font-bold cursor-pointer">▲ HIDE</button>
                    </div>
                </div>

                <div id="config-panel-body" class="space-y-4">
                    <!-- EXPIRATION & DTE FLOORS -->
                    <div class="bg-gray-950/60 p-3 rounded-lg border border-gray-800">
                        <div class="text-[10px] font-bold text-gray-300 uppercase tracking-wider mb-2">📅 EXPIRATION & DTE FLOORS</div>
                        <div class="space-y-3">
                            <div>
                                <div class="flex justify-between text-[11px] font-semibold text-gray-300 mb-1">
                                    <span>MIN DTE DEFAULT</span>
                                    <span id="val-min-dte" class="text-blue-400 font-bold bg-gray-900 px-2 py-0.5 rounded border border-gray-800">1 DAYS</span>
                                </div>
                                <input type="range" id="input-min-dte" min="0" max="14" value="1" oninput="document.getElementById('val-min-dte').innerText = this.value + ' DAYS'" class="w-full accent-blue-500 h-1.5 bg-gray-800 rounded-lg cursor-pointer">
                            </div>
                            <div>
                                <div class="flex justify-between text-[11px] font-semibold text-gray-300 mb-1">
                                    <span>LOW PRICE STOCK MIN DTE</span>
                                    <span id="val-low-dte" class="text-blue-400 font-bold bg-gray-900 px-2 py-0.5 rounded border border-gray-800">5 DAYS</span>
                                </div>
                                <input type="range" id="input-low-dte" min="1" max="30" value="5" oninput="document.getElementById('val-low-dte').innerText = this.value + ' DAYS'" class="w-full accent-blue-500 h-1.5 bg-gray-800 rounded-lg cursor-pointer">
                            </div>
                        </div>
                    </div>

                    <!-- RISK & CAPITAL BOUNDARIES -->
                    <div class="bg-gray-950/60 p-3 rounded-lg border border-gray-800">
                        <div class="text-[10px] font-bold text-gray-300 uppercase tracking-wider mb-2">🛡️ RISK & CAPITAL BOUNDARIES</div>
                        <div class="space-y-3">
                            <div>
                                <div class="flex justify-between text-[11px] font-semibold text-gray-300 mb-1">
                                    <span>LOW PRICE STOCK THRESHOLD</span>
                                    <span id="val-low-thresh" class="text-emerald-400 font-bold bg-gray-900 px-2 py-0.5 rounded border border-gray-800">$100</span>
                                </div>
                                <input type="range" id="input-low-thresh" min="10" max="500" step="5" value="100" oninput="document.getElementById('val-low-thresh').innerText = '$' + this.value" class="w-full accent-emerald-500 h-1.5 bg-gray-800 rounded-lg cursor-pointer">
                            </div>
                            <div>
                                <div class="flex justify-between text-[11px] font-semibold text-gray-300 mb-1">
                                    <span>MAX TRADE DOLLAR COST</span>
                                    <span id="val-max-cost" class="text-emerald-400 font-bold bg-gray-900 px-2 py-0.5 rounded border border-gray-800">$225</span>
                                </div>
                                <input type="range" id="input-max-cost" min="50" max="1000" step="25" value="225" oninput="document.getElementById('val-max-cost').innerText = '$' + this.value" class="w-full accent-emerald-500 h-1.5 bg-gray-800 rounded-lg cursor-pointer">
                            </div>
                        </div>
                    </div>

                    <!-- EXECUTION FILTERS & SCALPS -->
                    <div class="bg-gray-950/60 p-3 rounded-lg border border-gray-800 space-y-3">
                        <div class="text-[10px] font-bold text-gray-300 uppercase tracking-wider">⚡ EXECUTION FILTERS & SCALPS</div>
                        <div>
                            <div class="flex justify-between text-[11px] font-semibold text-gray-300 mb-1">
                                <span>MAX BID/ASK SPREAD CAP</span>
                                <span id="val-spread-cap" class="text-purple-400 font-bold bg-gray-900 px-2 py-0.5 rounded border border-gray-800">10%</span>
                            </div>
                            <input type="range" id="input-spread-cap" min="1" max="30" value="10" oninput="document.getElementById('val-spread-cap').innerText = this.value + '%'" class="w-full accent-purple-500 h-1.5 bg-gray-800 rounded-lg cursor-pointer">
                        </div>
                        <div class="flex items-center justify-between p-2 bg-gray-900 rounded border border-gray-800">
                            <label for="input-green-stays-green" class="cursor-pointer">
                                <div class="text-[11px] font-bold text-emerald-400">GREEN STAYS GREEN</div>
                                <div class="text-[9px] text-gray-400">LATE-DAY TRAILING STOP PROFIT LOCK (15:15 ET)</div>
                            </label>
                            <input type="checkbox" id="input-green-stays-green" checked class="w-4 h-4 accent-emerald-500 rounded cursor-pointer">
                        </div>
                    </div>
                     
                    <pre id="config-raw-json" class="p-3 bg-black text-amber-400 font-mono text-[10px] rounded border border-gray-800 overflow-x-auto shadow-inner hidden">> System Guards Engine Initialized.</pre>
                </div>
            </div>

            <!-- ACTIVE POSITIONS & CARDS -->
            <div>
                <h3 class="text-xs font-bold text-gray-300 uppercase tracking-wider mb-3">ACTIVE POSITIONS & RISK MATRIX</h3>
                <div id="active-cards-container" class="space-y-3 w-full"></div>
            </div>

            <!-- CLOSED POSITIONS -->
            <div>
                <h2 class="text-xs font-bold text-gray-400 uppercase mb-3 tracking-wider">CLOSED POSITIONS ({{ selected_date }})</h2>
                <div class="space-y-3">
                    {% for trade in closed_trades %}
                    <div class="bg-slate-900 border border-slate-800 rounded-lg p-3 flex flex-col gap-2">
                      <div class="flex justify-between items-center">
                        <div class="flex items-center gap-2">
                          <span class="font-bold text-white text-lg">{{ trade.ticker }}</span>
                          <span class="text-xs px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono">{{ trade.direction }}</span>
                          <span class="text-xs font-bold font-mono text-emerald-400">{{ trade.dollar_pnl }}</span>
                          <span class="text-xs px-2 py-0.5 rounded bg-amber-950 text-amber-400 font-mono border border-amber-800/80 font-bold">{{ trade.contracts }}x</span>
                          <span class="text-xs px-2 py-0.5 rounded bg-blue-950 text-blue-400 font-mono border border-blue-800">{{ trade.status }}</span>
                        </div>
                        <div class="text-right">
                          <span class="font-bold {{ trade.pnl_class }} text-lg">{{ trade.dollar_pnl }}</span>
                          <div class="text-xs text-slate-400">{{ trade.timestamp }}</div>
                        </div>
                      </div>

                      <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs bg-slate-950 p-2 rounded border border-slate-800/60 font-mono">
                        <div><span class="text-slate-500">Strategy:</span> <span class="text-slate-300">{{ trade.strategy }}</span></div>
                        <div><span class="text-slate-500">Entry/Exit:</span> <span class="text-slate-300">{{ trade.entry_price }} / {{ trade.exit_price }}</span></div>
                        <div><span class="text-slate-500">Stop Loss:</span> <span class="text-red-400">{{ trade.stop_loss }}</span></div>
                        <div><span class="text-slate-500">Target:</span> <span class="text-emerald-400">{{ trade.take_profit }}</span></div>
                      </div>

                      <div class="text-xs bg-slate-950/80 px-2 py-1 rounded border border-slate-800/40 text-slate-400 font-mono flex items-center gap-1">
                        <span class="text-amber-400 font-bold">📝 CSO Reason:</span> 
                        <span class="text-slate-300">{{ trade.cso_notes }}</span>
                      </div>
                    </div>
                    {% endfor %}
                </div>
            </div>

        </div>

        <!-- RIGHT COLUMN: Process Watchdog, System Health, & Proximity Matrix (5 Cols) -->
        <div class="lg:col-span-5 space-y-6">

            <!-- WATCHDOG & DAEMON SENTINEL PANEL -->
            <div class="bg-gray-900/90 border border-red-500/40 rounded-xl p-4 shadow-xl">
                <div class="flex items-center justify-between pb-3 mb-3 border-b border-gray-800">
                    <div class="flex items-center space-x-2">
                        <span class="relative flex h-3 w-3">
                          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                          <span class="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
                        </span>
                        <div>
                            <h2 class="text-xs font-bold text-red-400 tracking-wider uppercase">🐕 WATCHDOG SENTINEL</h2>
                            <p class="text-[9px] text-gray-400 font-mono">REAL-TIME SERVICE HEARTBEAT & HEALTH MONITOR</p>
                        </div>
                    </div>
                    <button onclick="fetchWatchdogStatus()" class="bg-gray-800 hover:bg-gray-700 text-gray-300 font-bold text-[10px] px-2 py-1 rounded border border-gray-700">
                        🔄 REFRESH
                    </button>
                </div>

                <!-- Global Health Badge -->
                <div id="watchdog-global-banner" class="mb-4 p-2.5 rounded-lg border bg-emerald-950/40 border-emerald-500/40 text-emerald-400 text-center text-xs font-bold font-mono">
                    🟢 ALL SERVICES ONLINE & HEALTHY
                </div>

                <!-- Daemon Status List -->
                <div id="watchdog-service-list" class="space-y-2.5 font-mono text-xs">
                    <!-- Dynamic Service Badges Render Here -->
                </div>
            </div>

            <!-- LEVEL PROXIMITY MATRIX -->
            <div class="bg-gray-900/90 border border-gray-800 rounded-xl p-4 shadow-xl">
                <h3 class="color-gray-400 text-xs font-bold tracking-wider mb-3 uppercase">LEVEL PROXIMITY MATRIX</h3>
                <div id="proximity-container" class="grid grid-cols-1 sm:grid-cols-2 gap-3"></div>
            </div>

        </div>

    </div>

    <script>
    function toggleConfigBody() {
        var body = document.getElementById("config-panel-body");
        var btn = document.getElementById("btn-toggle-config");
        body.classList.toggle("hidden");
        btn.innerText = body.classList.contains("hidden") ? "▼ SHOW" : "▲ HIDE";
    }
    function triggerConfigAudit() {
        var raw = document.getElementById("config-raw-json");
        raw.classList.remove("hidden");
        raw.innerText = "> Running Strategy Guard Audit...";
        fetch("/api/audit_config")
            .then(res => res.json())
            .then(data => {
                raw.innerText = "[⚡ AUDIT RESULT - " + data.timestamp + "]\nStatus: " + data.status + "\nActive Guards:\n" + JSON.stringify(data.active_guards, null, 2);
            });
    }
    function triggerAutoScout() {
        var raw = document.getElementById("config-raw-json");
        raw.classList.remove("hidden");
        raw.innerText = "> Launching Auto-Scout Engine across watchlists...";
        fetch("/api/auto_scout")
            .then(res => res.json())
            .then(data => {
                raw.innerText = "[🚀 AUTO-SCOUT RESULT - " + data.timestamp + "]\nStatus: " + data.status + "\nScouted Watchlist:\n" + JSON.stringify(data.scouted_targets, null, 2);
            });
    }
    function saveStrategyConfig() {
        var payload = {
            min_dte_default: parseInt(document.getElementById("input-min-dte").value),
            low_price_stock_min_dte: parseInt(document.getElementById("input-low-dte").value),
            low_price_stock_threshold: parseInt(document.getElementById("input-low-thresh").value),
            max_trade_dollar_cost: parseInt(document.getElementById("input-max-cost").value),
            max_bid_ask_spread_cap: parseInt(document.getElementById("input-spread-cap").value),
            green_stays_green: document.getElementById("input-green-stays-green").checked
        };
        fetch("/api/save_config", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        });
    }

    // --- WATCHDOG REAL-TIME STATUS POLLER ---
    async function fetchWatchdogStatus() {
        try {
            const res = await fetch("/api/watchdog_status");
            const data = await res.json();
            
            const banner = document.getElementById("watchdog-global-banner");
            const list = document.getElementById("watchdog-service-list");
            if (!banner || !list) return;

            if (data.system_status === "HEALTHY") {
                banner.className = "mb-4 p-2.5 rounded-lg border bg-emerald-950/40 border-emerald-500/40 text-emerald-400 text-center text-xs font-bold font-mono";
                banner.innerText = "🟢 ALL SERVICES ONLINE & HEALTHY";
            } else {
                banner.className = "mb-4 p-2.5 rounded-lg border bg-red-950/60 border-red-500/60 text-red-400 text-center text-xs font-bold font-mono animate-pulse";
                banner.innerText = "🚨 CRITICAL: SERVICE DEGRADATION / OFFLINE PROCESS DETECTED";
            }

            let html = "";
            for (const [svcName, svc] of Object.entries(data.services)) {
                const isOnline = svc.status === "ONLINE";
                const badgeBg = isOnline ? "bg-emerald-950 border-emerald-800 text-emerald-400" : "bg-red-950 border-red-800 text-red-400";
                const statusDot = isOnline ? "🟢" : "🔴";
                
                html += `
                    <div class="p-3 rounded-lg border ${badgeBg} flex items-center justify-between">
                        <div>
                            <div class="font-bold flex items-center gap-1.5">
                                <span>${statusDot}</span>
                                <span>${svcName}</span>
                            </div>
                            <div class="text-[10px] text-gray-400 mt-0.5">
                                PID: ${svc.pid ? svc.pid : 'OFFLINE'} | Script: ${svc.script}
                            </div>
                        </div>
                        <div class="text-right">
                            <div class="text-[10px] font-bold ${isOnline ? 'text-emerald-400' : 'text-red-400'}">
                                ${svc.status}
                            </div>
                            <div class="text-[9px] text-gray-500">${svc.last_ping}</div>
                        </div>
                    </div>
                `;
            }
            list.innerHTML = html;
        } catch (e) {
            console.error("Watchdog status poll error:", e);
        }
    }

    async function fetchProximity() {
        try {
            const res = await fetch("/api/proximity");
            const data = await res.json();
            const container = document.getElementById("proximity-container");
            if (!container) return;

            let html = "";
            for (const [ticker, info] of Object.entries(data)) {
                const statusBg = info.armed ? "rgba(0, 230, 118, 0.15)" : "rgba(255, 255, 255, 0.05)";
                const statusColor = info.armed ? "#00e676" : "#8f9bba";
                const statusText = info.status || (info.armed ? "ARMED" : "WAITING");

                const spot = (info.spot || 0).toFixed(2);
                const targetCall = (info.target_call || 0).toFixed(2);
                const targetPut = (info.target_put || 0).toFixed(2);

                html += `
                    <div style="background: #111827; border: 1px solid #1f293d; border-radius: 8px; padding: 10px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                            <span style="font-weight: 800; font-size: 14px; color: #ffffff;">${ticker}</span>
                            <span style="background: ${statusBg}; color: ${statusColor}; font-size: 9px; font-weight: 700; padding: 2px 6px; border-radius: 4px;">${statusText}</span>
                        </div>
                        <div style="font-size: 11px; color: #8f9bba; display: flex; justify-content: space-between; margin-bottom: 2px;">
                            <span>Spot: <strong style="color: #fff;">$${spot}</strong></span>
                            <span>Prox: <strong style="color: #ffb74d;">${info.prox || 0}%</strong></span>
                        </div>
                        <div style="font-size: 11px; color: #8f9bba; display: flex; justify-content: space-between;">
                            <span>Call: <strong style="color: #00e676;">$${targetCall}</strong></span>
                            <span>Put: <strong style="color: #ef4444;">$${targetPut}</strong></span>
                        </div>
                    </div>
                `;
            }
            container.innerHTML = html;
        } catch (e) {
            console.error("Proximity fetch error:", e);
        }
    }

    async function renderActiveCards() {
        try {
            const res = await fetch('/dashboard_data.json');
            const data = await res.json();
            const container = document.getElementById('active-cards-container');
            if (!container) return;

            const items = data.active_positions || data.active_trade_cards || [];
            if (items.length === 0) {
                container.innerHTML = '<div style="color: #6c757d; font-style: italic;" class="text-xs">No Active Positions Deployed</div>';
                return;
            }

            container.innerHTML = items.map(item => `
                <div style="background: #1e222d; border: 1px solid #2a2e3d; border-radius: 8px; padding: 12px; width: 100%;">
                    <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #2a2e3d; padding-bottom: 6px; margin-bottom: 8px;">
                        <span style="font-weight: bold; color: #fff;">${item.ticker} <span style="color: #00bc8c;">${item.direction}</span></span>
                        <span style="background: #2b3245; padding: 2px 8px; border-radius: 4px; color: #ffb74d; font-size: 0.8em;">${item.gex_engagement || 'TARGET'}</span>
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; font-size: 0.85em; color: #ccc;">
                        <div><span style="color: #848e9c;">Entry:</span> $${item.entry_price}</div>
                        <div><span style="color: #848e9c;">Bid/Ask:</span> $${item.current_bid}/$${item.current_ask}</div>
                        <div><span style="color: #848e9c;">Fill Score:</span> <b style="color:#00bc8c;">${item.fill_quality_score}/10</b></div>
                        <div><span style="color: #848e9c;">Confidence:</span> <b>${item.confidence_status || item.confidence_score}</b></div>
                    </div>
                    <div style="margin-top: 8px; padding-top: 6px; border-top: 1px dashed #2a2e3d; display: flex; justify-content: space-between; font-size: 0.85em;">
                        <span style="color: #848e9c;">PNL:</span>
                        <span style="font-weight: bold; color: ${item.pnl_dollars >= 0 ? '#00c853' : '#ff5252'};">
                            ${item.pnl_dollars >= 0 ? '+' : ''}$${item.pnl_dollars} (${item.pnl_pct}%)
                        </span>
                    </div>
                </div>
            `).join('');
        } catch (e) {
            console.error("Error rendering active cards:", e);
        }
    }

    // Initialize Auto-Polling
    fetchWatchdogStatus();
    setInterval(fetchWatchdogStatus, 5000);
    fetchProximity();
    setInterval(fetchProximity, 3000);
    setInterval(renderActiveCards, 3000);
    document.addEventListener('DOMContentLoaded', renderActiveCards);
    </script>
</body>
</html>
"""

def get_db_connection():
    db_path = "/app/harm_telemetry.db" if os.path.exists("/app/harm_telemetry.db") else DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# WATCHDOG DAEMON AUDIT ENDPOINT
@app.get("/api/watchdog_status")
def get_watchdog_status():
    monitored = {
        "LiveBot": "src/LiveBot.py",
        "GexExitMonitor": "src/gex_exit_monitor.py",
        "ActiveRiskDaemon": "src/active_risk_daemon.py",
        "BotStreamer": "harmonized_bot_streamer.py"
    }
    
    status_map = {}
    system_degraded = False

    try:
        ps_out = subprocess.check_output(["ps", "aux"]).decode()
    except Exception:
        ps_out = ""

    for svc_name, script_path in monitored.items():
        is_running = script_path in ps_out
        
        # Extract PID if running
        pid = None
        if is_running:
            for line in ps_out.splitlines():
                if script_path in line:
                    parts = line.split()
                    if len(parts) > 1:
                        pid = parts[1]
                        break

        if not is_running:
            system_degraded = True

        status_map[svc_name] = {
            "status": "ONLINE" if is_running else "OFFLINE",
            "script": script_path,
            "pid": pid,
            "last_ping": datetime.now().strftime("%H:%M:%S ET") if is_running else "NO_HEARTBEAT"
        }

    return {
        "system_status": "DEGRADED" if system_degraded else "HEALTHY",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S ET"),
        "services": status_map
    }

def get_live_quote(symbol):
    token = os.getenv("TRADIER_TOKEN") or os.getenv("TRADIER_SANDBOX_TOKEN")
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    base_url = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1")
    try:
        r = requests.get(f"{base_url}/markets/quotes?symbols={symbol}", headers=headers, timeout=3)
        if r.status_code == 200:
            quote = r.json().get('quotes', {}).get('quote', {})
            return quote[0] if isinstance(quote, list) else quote
    except Exception as e:
        pass
    return {}

def fetch_tradier_balances(env=None):
    from dotenv import dotenv_values
    passed_env = str(env or "").upper()
    exec_env = str(os.getenv("EXECUTION_ENV", "")).upper()
    tradier_env = str(os.getenv("TRADIER_ENV", "")).upper()
    acct_id = str(os.getenv("TRADIER_ACCOUNT_ID", ""))
    
    is_prod = (passed_env in ["PROD", "PRODUCTION", "LIVE"] or exec_env in ["PROD", "PRODUCTION", "LIVE"] or acct_id == "6YB87601")

    if is_prod:
        p_env = dotenv_values(".env.prod") if os.path.exists(".env.prod") else {}
        token = os.getenv("TRADIER_ACCESS_TOKEN") or p_env.get("TRADIER_ACCESS_TOKEN") or os.getenv("TRADIER_TOKEN")
        acct = os.getenv("TRADIER_ACCOUNT_ID") or p_env.get("TRADIER_ACCOUNT_ID") or "6YB87601"
        base_url = "https://api.tradier.com/v1"
    else:
        sb_env = dotenv_values(".env.sandbox") if os.path.exists(".env.sandbox") else {}
        token = sb_env.get("TRADIER_ACCESS_TOKEN") or sb_env.get("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_SANDBOX_TOKEN")
        acct = sb_env.get("TRADIER_ACCOUNT_ID") or "VA83416608"
        base_url = "https://sandbox.tradier.com/v1"

    if not token or not acct:
        return (113210.62, 113210.62, 0.0) if CURRENT_ENV != "PROD" else (453.26, 453.26, 0.0)

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        url = f"{base_url}/accounts/{acct}/balances"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            bal = r.json().get("balances", {})
            equity = float(bal.get("total_equity", 0.0) or 0.0)
            cash = float(bal.get("total_cash", bal.get("cash", {}).get("cash_available", 0.0)) or 0.0)
            unsettled = float(bal.get("uncleared_funds", bal.get("unsettled_funds", 0.0)) or 0.0)
            return equity, cash, unsettled
    except Exception as e:
        pass

    return (113210.62, 113210.62, 0.0) if CURRENT_ENV != "PROD" else (453.26, 453.26, 0.0)

def close_position_in_db(ticker_to_close, exit_price=None, tenant_id='COMPANY_A_PROD'):
    db_path = "/app/harm_telemetry.db" if os.path.exists("/app/harm_telemetry.db") else DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM trades WHERE ticker = ? AND exit_status = 'ACTIVE'", (ticker_to_close,))
    trade = cursor.fetchone()

    if not trade:
        conn.close()
        return False

    entry_cost = float(trade['entry_price'] or 0.0)
    shares = int(trade['shares'] or 1)
    exit_price = entry_cost * 1.05

    realized_pnl = round((exit_price - entry_cost) * 100 * shares, 2)

    cursor.execute('''
        UPDATE trades 
        SET exit_status = 'FORCE_CLOSE', exit_price = ?, net_pnl = ? 
        WHERE ticker = ? AND exit_status = 'ACTIVE'
    ''', (exit_price, realized_pnl, ticker_to_close))

    conn.commit()
    conn.close()
    return True

def enrich_active_positions_with_live_quotes(trades):
    token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
    base_url = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1" if CURRENT_ENV not in ["PROD", "PRODUCTION", "LIVE"] else "https://api.tradier.com/v1")
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    total_deployed_basis = 0.0
    total_floating_pnl_val = 0.0

    for t in trades:
        tkr = str(t.get('ticker', '')).upper()
        opt_cost = float(t.get('entry_price') or t.get('basis') or t.get('cost') or 0.80)
        shares_cnt = float(t.get('shares', 1.0))
        direction = resolve_trade_direction(t)

        occ = str(t.get('occ_symbol', ''))
        t['direction'] = direction
        t['cost'] = f"{opt_cost:.2f}"
        t['basis'] = f"{opt_cost:.2f}"

        opt_mark = opt_cost
        if occ and token:
            try:
                q = requests.get(f"{base_url}/markets/quotes", params={"symbols": occ}, headers=headers, timeout=2).json()
                quote = q.get("quotes", {}).get("quote", {})
                if isinstance(quote, list) and len(quote) > 0:
                    quote = quote[0]
                bid = float(quote.get("bid") or 0.0)
                ask = float(quote.get("ask") or 0.0)
                opt_mark = round((bid + ask) / 2.0, 2) if (bid and ask) else float(quote.get("last") or opt_cost)
            except Exception:
                opt_mark = float(t.get('option_mark') or opt_cost)

        t['option_mark'] = opt_mark
        t['price'] = f"{opt_mark:.2f}"
        t['shares'] = shares_cnt

        opt_sl = float(t.get('stop_loss') or (opt_cost * 0.80))
        opt_tp = float(t.get('take_profit') or (opt_cost * 1.50))
        t['stop_display'] = f"${opt_sl:.2f}"

        dollar_pnl_val = round((opt_mark - opt_cost) * 100.0 * shares_cnt, 2)
        pct_pnl_val = round((dollar_pnl_val / (opt_cost * shares_cnt * 100.0)) * 100.0, 1) if opt_cost > 0 else 0.0

        t['net_pnl'] = dollar_pnl_val
        pnl_prefix = '+' if dollar_pnl_val >= 0 else ''
        t['dollar_pnl'] = f"{pnl_prefix}${dollar_pnl_val:.2f}"
        t['pnl_pct'] = f"{pnl_prefix}{pct_pnl_val:.1f}%"
        t['pnl_class'] = 'text-emerald-400' if dollar_pnl_val >= 0 else 'text-red-400'

        total_deployed_basis += (opt_cost * shares_cnt * 100.0)
        total_floating_pnl_val += dollar_pnl_val

    return trades, total_deployed_basis, total_floating_pnl_val

def fetch_portfolio_state(page=1, selected_date=None, tenant_id="COMPANY_A_PROD", env=None):
    if not env:
        acct_id = os.getenv("TRADIER_ACCOUNT_ID", "")
        exec_env = os.getenv("EXECUTION_ENV", "").upper()
        tradier_env = os.getenv("TRADIER_ENV", "").upper()
        if exec_env in ["PROD", "PRODUCTION", "LIVE"] or tradier_env in ["PROD", "PRODUCTION", "LIVE"] or acct_id == "6YB87601":
            env = "PROD"
        else:
            env = "SANDBOX" 
    if not selected_date:
        selected_date = datetime.now().strftime("%Y-%m-%d")
         
    active_trades = fetch_all_active_dynamo_positions()
    db_closed = fetch_closed_dynamo_positions(selected_date)
    enriched_trades, total_deployed_basis, total_floating_pnl_val = enrich_active_positions_with_live_quotes(active_trades)
    total_closed_pnl = sum(float(t.get("net_pnl", 0.0)) for t in db_closed)
    starting_balance, settled_free, unsettled = fetch_tradier_balances(env=env)

    return enriched_trades, db_closed, total_floating_pnl_val, total_closed_pnl, selected_date, starting_balance, settled_free, total_deployed_basis, unsettled

@app.get("/api/proximity")
def get_proximity_api():
    levels_path = "trading_levels.json"
    levels = {}
    if os.path.exists(levels_path):
        try:
            with open(levels_path, "r", encoding="utf-8") as f:
                levels = json.load(f)
        except Exception:
            pass

    if "levels" in levels and isinstance(levels["levels"], dict):
        levels = levels["levels"]
    elif "data" in levels and isinstance(levels["data"], dict):
        levels = levels["data"]

    response = {}
    for ticker, info in levels.items():
        if not isinstance(info, dict):
            continue
        spot = info.get("spot_price") or info.get("spot") or info.get("current_price") or 0
        target_call = info.get("spot_target_call") or info.get("target_call") or info.get("call_target") or 0
        target_put = info.get("spot_target_put") or info.get("target_put") or info.get("put_target") or 0
        status = info.get("status") or "WAITING"
        armed = status == "ARMED" or info.get("execution_armed", False) or info.get("armed", False)
        
        response[ticker] = {
            "armed": armed,
            "spot": spot,
            "target_call": target_call,
            "target_put": target_put,
            "status": status,
            "prox": info.get("proximity_score") or info.get("prox") or info.get("proximity_pct", 0)
        }
    return response

@app.get("/", response_class=HTMLResponse)
async def index_view(request: Request, selected_date: str = Query(default=None)):
    trades, closed, total_pnl, total_closed_pnl, current_date, starting_balance, settled_free, deployed_capital, unsettled = fetch_portfolio_state(page=1, selected_date=selected_date)

    levels_data = {}
    if os.path.exists('trading_levels.json'):
        try:
            with open('trading_levels.json', 'r') as lf:
                levels_data = json.load(lf)
        except Exception:
            pass

    if "levels" in levels_data and isinstance(levels_data["levels"], dict):
        levels_data = levels_data["levels"]

    str_starting = f"${starting_balance:,.2f}" 
    str_settled = f"${settled_free:,.2f}"
    str_deployed = f"${deployed_capital:,.2f}"
    str_unsettled = f"${unsettled:,.2f}"
    pnl_prefix_total = '+' if total_pnl >= 0 else ''
    str_floating = f"{pnl_prefix_total}${total_pnl:,.2f}"
    str_realized = f"${total_closed_pnl:+.2f}"

    formatted_closed = []
    for item in closed:
        d = item if isinstance(item, dict) else (item._asdict() if hasattr(item, '_asdict') else dict(item))
        entry = float(d.get('entry_price', 0) or 0.0)
        exit_px = float(d.get('exit_price', 0) or 0.0)
        shares = int(float(d.get('shares', 1) or 1))
        pnl_val = float(d.get('net_pnl', 0.0) or 0.0)
        sl_val = d.get('stop_loss') or (entry * 0.8)
        tp_val = d.get('take_profit') or (entry * 1.5)

        formatted_closed.append({
            'ticker': d.get('ticker', 'N/A'),
            'direction': resolve_trade_direction(d),
            'strategy': d.get('strategy', 'SMART_CSO_LIVE'),
            'entry_price': f"${entry:.2f}",
            'exit_price': f"${exit_px:.2f}",
            'stop_loss': f"${float(sl_val):.2f}" if isinstance(sl_val, (int, float)) else str(sl_val),
            'take_profit': f"${float(tp_val):.2f}" if isinstance(tp_val, (int, float)) else str(tp_val),
            'cso_notes': str(d.get('cso_notes') or d.get('exit_status') or 'CLOSED'),
            'status': str(d.get('exit_status') or 'CLOSED'),
            'contracts': str(shares),
            'dollar_pnl': f"${pnl_val:+.2f}",
            'pnl_class': 'text-red-400' if pnl_val < 0 else 'text-emerald-400',
            'timestamp': d.get('exit_timestamp') or d.get('timestamp') or ''
        })

    template = Template(INDEX_HTML_TEMPLATE)
    rendered_html = template.render(
        str_starting=str_starting,
        str_settled=str_settled,
        str_deployed=str_deployed,
        str_unsettled=str_unsettled,
        proximity_matrix=levels_data,
        trades=trades,
        closed_trades=formatted_closed,
        selected_date=current_date,
        total_pnl=str_floating,
        pnl_class="text-emerald-400" if total_pnl >= 0 else "text-red-400",
        total_closed_pnl=str_realized,
        closed_pnl_class="text-emerald-400" if total_closed_pnl >= 0 else "text-red-400"
    )
    return HTMLResponse(content=rendered_html)

@app.get("/dashboard_data.json")
async def get_dashboard_data_json():
    try:
        if os.path.exists("dashboard_data.json"):
            with open("dashboard_data.json", "r") as f:
                return json.load(f)
        trades, closed, total_pnl, total_closed_pnl, current_date, starting_balance, settled_free, deployed_capital, unsettled = fetch_portfolio_state()
        return {
            "active_positions": trades,
            "active_trade_cards": trades,
            "closed_positions": closed,
            "deployed_capital": deployed_capital,
            "floating_pnl": f"${total_pnl:.2f}",
            "status": "success"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

CONFIG_FILE = "dashboard_config.json"
DEFAULT_CONFIG = {
    "min_dte_default": 1,
    "low_price_stock_min_dte": 5,
    "low_price_stock_threshold": 100,
    "max_trade_dollar_cost": 225,
    "max_bid_ask_spread_cap": 10,
    "green_stays_green": True
}

def load_dashboard_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

@app.get("/api/config")
def get_config():
    return load_dashboard_config()

@app.post("/api/save_config")
async def save_config(request: Request):
    try:
        data = await request.json()
        current = load_dashboard_config()
        current.update(data)
        with open(CONFIG_FILE, "w") as f:
            json.dump(current, f, indent=4)
        return {"status": "success", "config": current}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8080)
