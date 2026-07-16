import os
import sys
import json
import sqlite3
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environmental variables (.env)
load_dotenv()

# Path configuration - Using 100% markdown-safe pathing (no double underscores)
CURRENT_DIR = os.getcwd()
DB_FILE = os.path.join(CURRENT_DIR, 'harm_telemetry.db')
DATA_JSON = os.path.join(CURRENT_DIR, 'dashboard_data.json')
LEVELS_FILE = os.path.join(CURRENT_DIR, 'trading_levels.json')

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [STREAMER] {msg}")

class HarmonizedBotStreamer:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.active_monitors = {}  # In-memory fast cache for active trades
        
        # Ensure database tables exist with clean Unified structure
        self.init_database()
        
        # Pull any previously open trades upon boot to resume tracking
        self.sync_active_positions_from_db()

    def init_database(self):
        """Initializes trades telemetry table inside the local database."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                strategy TEXT NOT NULL,
                direction TEXT NOT NULL,
                support_level REAL,
                spot_price REAL,            -- Entry Price
                exit_price REAL,
                stop_loss REAL,
                take_profit REAL,
                distance REAL,
                allowed_dist REAL,
                proximity_score REAL,
                exit_status TEXT,           -- 'ACTIVE', 'TAKE_PROFIT', 'STOP_LOSS', 'FORCE_CLOSE'
                net_pnl REAL
            )
        """)
        conn.commit()
        conn.close()
        log_msg("[✓] Trade telemetry database verified and active.")

    def sync_active_positions_from_db(self):
        """Pulls active positions from database into standard Python dictionary for sub-millisecond checks."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, ticker, spot_price, stop_loss, take_profit, strategy, direction 
            FROM trades 
            WHERE exit_status = 'ACTIVE'
        """)
        rows = cursor.fetchall()
        conn.close()

        self.active_monitors = {}
        for r in rows:
            db_id, ticker, entry_p, sl, tp, strategy, direction = r
            if ticker not in self.active_monitors:
                self.active_monitors[ticker] = []
                
            self.active_monitors[ticker].append({
                "db_id": db_id,
                "entry_price": entry_p,
                "stop_loss": sl,
                "take_profit": tp,
                "strategy": strategy,
                "direction": direction
            })
        
        if len(self.active_monitors) > 0:
            log_msg(f"[⚙️] Resumed tracking on {len(rows)} active trades across: {list(self.active_monitors.keys())}")

    def inject_mock_active_trade(self, ticker, direction="CALL"):
        """Utility function to simulate manual entries for immediate system testing."""
        if not os.path.exists(LEVELS_FILE):
            log_msg("[!] Cannot inject trade: trading_levels.json not found.")
            return
            
        with open(LEVELS_FILE, 'r') as f:
            levels = json.load(f).get("levels", {})
            
        ticker_levels = levels.get(ticker, {})
        support_list = ticker_levels.get("algo_macro", {}).get("support", [])
        
        if not support_list:
            log_msg(f"[!] {ticker} has no support floor configured. Injection aborted.")
            return

        support_floor = float(support_list[0])
        entry_price = support_floor + 0.50  # Simulate entry close to support
        
        # Frame stop and targets
        stop_loss = entry_price - 1.50 if direction == "CALL" else entry_price + 1.50
        take_profit = entry_price + 3.00 if direction == "CALL" else entry_price - 3.00
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO trades (ticker, timestamp, strategy, direction, support_level, spot_price, exit_price, stop_loss, take_profit, distance, allowed_dist, proximity_score, exit_status, net_pnl)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticker, 
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
            "MANUAL_ENTRY", 
            direction, 
            support_floor, 
            entry_price, 
            stop_loss, 
            take_profit, 
            0.50,
            2.50,
            80.0, 
            "ACTIVE", 
            0.0
        ))
        conn.commit()
        conn.close()
        
        log_msg(f"[📥] INJECTED TEST POSITION: {ticker} {direction} entered at ${entry_price:.2f} (SL: ${stop_loss:.2f} | TP: ${take_profit:.2f})")
        self.sync_active_positions_from_db()

    def process_tick(self, ticker, spot_price):
        """High-performance tick evaluation engine."""
        if ticker not in self.active_monitors or not self.active_monitors[ticker]:
            return

        for position in self.active_monitors[ticker][:]:
            db_id = position["db_id"]
            entry_price = position["entry_price"]
            sl = position["stop_loss"]
            tp = position["take_profit"]
            direction = position["direction"]

            triggered_close = False
            outcome = None

            if direction == "CALL":
                if spot_price >= tp:
                    triggered_close = True
                    outcome = "TAKE_PROFIT"
                elif spot_price <= sl:
                    triggered_close = True
                    outcome = "STOP_LOSS"
            elif direction == "PUT":
                if spot_price <= tp:
                    triggered_close = True
                    outcome = "TAKE_PROFIT"
                elif spot_price >= sl:
                    triggered_close = True
                    outcome = "STOP_LOSS"

            if triggered_close:
                # Calculate Option premium returns (5 contracts, 0.50 delta proxy)
                price_delta = spot_price - entry_price if direction == "CALL" else entry_price - spot_price
                net_pnl = 5 * (price_delta * 0.50) * 100.0
                
                log_msg(f"[🔔] TRIGGER CRITERIA REACHED: {ticker} {direction} reached {outcome} limit at ${spot_price:.2f}!")
                self.execute_realtime_close(db_id, ticker, spot_price, outcome, net_pnl, position)

    def execute_realtime_close(self, db_id, ticker, exit_price, outcome, net_pnl, position_obj):
        """Persists closed metrics natively on EC2 disk and auto-regenerates dashboard file."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE trades 
            SET exit_status = ?, exit_price = ?, net_pnl = ?
            WHERE id = ?
        """, (outcome, exit_price, round(net_pnl, 2), db_id))
        conn.commit()
        conn.close()

        log_msg(f"[✓] DB updated successfully. {ticker} trade #{db_id} committed with return: ${net_pnl:+.2f}")
        
        self.active_monitors[ticker].remove(position_obj)
        if not self.active_monitors[ticker]:
            del self.active_monitors[ticker]
            
        self.regenerate_dashboard_json()

    def regenerate_dashboard_json(self):
        """Compiles SQL statistics and outputs a live JSON manifest for dashboard visualizations."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*), SUM(net_pnl), SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) FROM trades")
        total_t, net_pnl, wins = cursor.fetchone()
        
        net_pnl = net_pnl if net_pnl else 0.0
        win_rate = round((wins / total_t) * 100.0, 2) if total_t and total_t > 0 else 0.0
        
        buckets = [
            {"min": 80, "max": 100, "name": "Elite Proximity (80%-100%)"},
            {"min": 50, "max": 80, "name": "Moderate Proximity (50%-80%)"},
            {"min": 0, "max": 50, "name": "Fringe Proximity (0%-50%)"}
        ]
        
        bucket_stats = []
        for b in buckets:
            cursor.execute("""
                SELECT COUNT(*), SUM(net_pnl), SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END)
                FROM trades 
                WHERE proximity_score >= ? AND proximity_score < ?
            """, (b["min"], b["max"]))
            count, pnl, b_wins = cursor.fetchone()
            
            b_pnl = round(pnl, 2) if pnl else 0.0
            b_wr = round((b_wins / count) * 100.0, 2) if count and count > 0 else 0.0
            
            bucket_stats.append({
                "range": b["name"],
                "trades": count or 0,
                "win_rate": b_wr,
                "net_pnl": b_pnl
            })

        cursor.execute("""
            SELECT ticker, timestamp, strategy, direction, proximity_score, exit_status, net_pnl 
            FROM trades 
            ORDER BY timestamp DESC
        """)
        raw_rows = cursor.fetchall()
        
        trade_history = []
        for r in raw_rows:
            trade_history.append({
                "ticker": r[0],
                "timestamp": r[1],
                "strategy": r[2],
                "direction": r[3],
                "proximity": r[4] if r[4] else 0.0,
                "status": r[5],
                "pnl": r[6] if r[6] else 0.0
            })
            
        conn.close()
        
        payload = {
            "overall": {
                "total_trades": total_t,
                "net_pnl": round(net_pnl, 2),
                "win_rate": win_rate
            },
            "buckets": bucket_stats,
            "history": trade_history
        }
        
        temp_file = f"{DATA_JSON}.tmp"
        with open(temp_file, 'w') as f:
            json.dump(payload, f, indent=4)
        os.replace(temp_file, DATA_JSON)
        log_msg("[✓] Live HTML Dashboard JSON dataset refreshed.")

    async def start_websocket_stream(self, tickers):
        """Establishes continuous streaming connections to track actual underlying trades."""
        headers = {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret
        }
        
        url = f"https://data.alpaca.markets/v2/stocks/snapshots?symbols={','.join(tickers)}"
        log_msg(f"Initiating high-frequency streaming core for watchlist: {tickers}")

        while True:
            try:
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    payload = response.json()
                    if payload and isinstance(payload, dict):
                        for ticker in tickers:
                            ticker_data = payload.get(ticker, {})
                            latest_trade = ticker_data.get("latestTrade", {})
                            
                            if latest_trade and latest_trade.get("p"):
                                spot_price = float(latest_trade.get("p"))
                                self.process_tick(ticker, spot_price)
                
                self.sync_active_positions_from_db()
                
            except Exception as e:
                log_msg(f"[─] Snapshot tick error: {e}")
                
            await asyncio.sleep(1.0)

if os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID"):
    KEY = os.getenv("ALPACA_API_KEY") or os.getenv("APCA_API_KEY_ID")
    SECRET = os.getenv("ALPACA_SECRET_KEY") or os.getenv("APCA_API_SECRET_KEY")
    
    streamer = HarmonizedBotStreamer(KEY, SECRET)
    watchlist_symbols = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "AMZN", "MSFT"]
    
    try:
        asyncio.run(streamer.start_websocket_stream(watchlist_symbols))
    except KeyboardInterrupt:
        log_msg("Streaming core terminated cleanly by operator.")
else:
    log_msg("[!] Error: No Alpaca keys found inside .env file.")
