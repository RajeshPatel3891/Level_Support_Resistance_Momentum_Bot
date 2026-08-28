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

# Tradier API Configuration
TRADIER_TOKEN = os.getenv("TRADIER_TOKEN") or os.getenv("TRADIER_SANDBOX_TOKEN")
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
ACTIVE_TICKERS = [t.strip() for t in os.getenv("ACTIVE_TICKERS", "F,SOFI,AAL,RIVN").split(",") if t.strip()]

# Path configuration
CURRENT_DIR = os.getcwd()
DB_FILE = os.path.join(CURRENT_DIR, 'harm_telemetry.db')
DATA_JSON = os.path.join(CURRENT_DIR, 'dashboard_data.json')
LEVELS_FILE = os.path.join(CURRENT_DIR, 'trading_levels.json')

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [STREAMER] {msg}")

class HarmonizedBotStreamer:
    def __init__(self, tradier_token=None, tradier_base_url=None):
        self.tradier_token = tradier_token or TRADIER_TOKEN
        self.tradier_base_url = tradier_base_url or TRADIER_BASE_URL
        self.active_tickers = ACTIVE_TICKERS
        self.active_monitors = {}  # In-memory fast cache for active trades
        
        # Momentum & Smart CSO Entry Buffers
        self.prev_spots = {}      # Ticker -> previous spot price
        self.green_ticks = {}     # Ticker -> count of consecutive green ticks
        
        self.init_database()
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
        """Pulls active positions from database into standard Python dictionary."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        import os
        target_env = os.getenv("EXECUTION_ENV", os.getenv("TRADIER_ENV", "SANDBOX")).upper()
        if target_env in ["PROD", "PRODUCTION", "LIVE"]:
            cursor.execute("SELECT * FROM trades WHERE exit_status = 'ACTIVE' AND (execution_env = 'PRODUCTION' OR is_live = 1)")
        else:
            cursor.execute("SELECT * FROM trades WHERE exit_status = 'ACTIVE' AND (execution_env = 'SANDBOX' OR is_live = 0)")
        rows = cursor.fetchall()
        conn.close()

        self.active_monitors = {}
        for row in rows:
            ticker = row["ticker"]
            if ticker not in self.active_monitors:
                self.active_monitors[ticker] = []
                
            keys = row.keys()
            occ = row["occ_symbol"] if "occ_symbol" in keys else (row["option_symbol"] if "option_symbol" in keys else ticker)
            shares = abs(float(row["shares"])) if ("shares" in keys and row["shares"]) else 5.0
            entry_p = float(row["spot_price"] or row["entry_price"] or 0.0)
            
            self.active_monitors[ticker].append({
                "db_id": row["id"],
                "entry_price": entry_p,
                "stop_loss": float(row["stop_loss"] or round(entry_p * 0.80, 2)),
                "take_profit": float(row["take_profit"] or round(entry_p * 1.50, 2)),
                "strategy": str(row["strategy"]),
                "direction": str(row["direction"]),
                "occ_symbol": str(occ),
                "shares": shares
            })

    def update_levels_file_spot_prices(self, quotes_dict):
        """Updates live spot prices inside trading_levels.json."""
        if not os.path.exists(LEVELS_FILE):
            return
            
        try:
            with open(LEVELS_FILE, 'r') as f:
                data = json.load(f)
                
            levels = data.get("levels") if (isinstance(data, dict) and "levels" in data) else data
            if not isinstance(levels, dict):
                return

            updated = False
            for ticker, live_spot in quotes_dict.items():
                if ticker in levels and live_spot is not None:
                    levels[ticker]["spot"] = live_spot
                    updated = True
                    
            if updated:
                temp_file = f"{LEVELS_FILE}.tmp"
                with open(temp_file, 'w') as f:
                    json.dump(data, f, indent=4)
                os.replace(temp_file, LEVELS_FILE)
        except Exception as e:
            log_msg(f"[!] Error updating trading_levels.json spot prices: {e}")

    def validate_smart_cso_entry(self, ticker, spot, vwap, direction, option_quote=None):
        """
        Smart CSO Entry Guard:
        1. Momentum: Requires >= 3 consecutive green ticks.
        2. Trend: Spot > VWAP for CALL, Spot < VWAP for PUT.
        3. Liquidity: Option Bid >= $0.05 and Spread <= 15%.
        """
        # 1. Momentum Check (3 consecutive green ticks)
        consecutive_green = self.green_ticks.get(ticker, 0)
        if consecutive_green < 3:
            log_msg(f"[🛡️ GUARD REJECTED] {ticker}: Insufficient momentum ({consecutive_green}/3 green ticks).")
            return False

        # 2. VWAP Trend Alignment
        if vwap > 0:
            if direction == "CALL" and spot <= vwap:
                log_msg(f"[🛡️ GUARD REJECTED] {ticker}: CALL entry blocked (Spot ${spot:.2f} <= VWAP ${vwap:.2f}).")
                return False
            elif direction == "PUT" and spot >= vwap:
                log_msg(f"[🛡️ GUARD REJECTED] {ticker}: PUT entry blocked (Spot ${spot:.2f} >= VWAP ${vwap:.2f}).")
                return False

        # 3. Bid-Ask Spread Guard (If Option Quote Provided)
        if option_quote and isinstance(option_quote, dict):
            bid = float(option_quote.get("bid") or 0.0)
            ask = float(option_quote.get("ask") or 0.0)
            
            if bid < 0.05:
                log_msg(f"[🛡️ GUARD REJECTED] {ticker}: Option bid ${bid:.2f} is too low / illiquid.")
                return False
                
            if ask > 0:
                spread_pct = (ask - bid) / ask
                if spread_pct > 0.15:
                    log_msg(f"[🛡️ GUARD REJECTED] {ticker}: Option spread too wide ({spread_pct * 100.0:.1f}%).")
                    return False

        log_msg(f"[🟢 SMART CSO PASSED] {ticker}: All entry guards passed! Executing entry.")
        return True

    def process_tick(self, ticker, spot_price, vwap_price=0.0):
        """High-performance tick evaluation & exit engine."""
        # Update Momentum Tracker (Green Tick Counter)
        prev_spot = self.prev_spots.get(ticker)
        if prev_spot is not None:
            if spot_price > prev_spot:
                self.green_ticks[ticker] = self.green_ticks.get(ticker, 0) + 1
            elif spot_price < prev_spot:
                self.green_ticks[ticker] = 0  # Reset counter immediately on red tick
        self.prev_spots[ticker] = spot_price

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
                price_delta = spot_price - entry_price if direction == "CALL" else entry_price - spot_price
                net_pnl = 5 * (price_delta * 0.50) * 100.0
                
                log_msg(f"[🔔] TRIGGER CRITERIA REACHED: {ticker} {direction} reached {outcome} limit at ${spot_price:.2f}!")
                self.execute_realtime_close(db_id, ticker, spot_price, outcome, net_pnl, position)

    def execute_realtime_close(self, db_id, ticker, exit_price, outcome, net_pnl, position_obj):
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

    def fetch_tradier_quotes(self, tickers=None):
        symbols_list = tickers or self.active_tickers
        symbols = ",".join(symbols_list) if isinstance(symbols_list, list) else symbols_list
        url = f"{self.tradier_base_url}/markets/quotes"
        headers = {
            "Authorization": f"Bearer {self.tradier_token}",
            "Accept": "application/json"
        }
        params = {"symbols": symbols, "greeks": "false"}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json()
                quotes = data.get("quotes", {}).get("quote", [])
                if isinstance(quotes, dict):
                    quotes = [quotes]
                return {
                    q["symbol"]: {
                        "last": float(q["last"]),
                        "vwap": float(q.get("vwap") or q["last"])
                    }
                    for q in quotes 
                    if q and "symbol" in q and "last" in q and q["last"] is not None
                }
        except Exception as e:
            log_msg(f"[!] Error fetching Tradier quotes: {e}")
        return {}

    async def start_tradier_stream(self, tickers=None):
        watch_list = tickers or self.active_tickers
        log_msg(f"Initiating Smart Tradier quote streamer with Green-Tick & VWAP Guards: {watch_list}")

        while True:
            try:
                quotes = self.fetch_tradier_quotes(watch_list)
                if quotes:
                    spot_dict = {t: q["last"] for t, q in quotes.items()}
                    self.update_levels_file_spot_prices(spot_dict)
                    
                    for ticker, qdata in quotes.items():
                        spot_price = qdata["last"]
                        vwap_price = qdata["vwap"]
                        self.process_tick(ticker, spot_price, vwap_price)
                
                self.sync_active_positions_from_db()
                
            except Exception as e:
                log_msg(f"[─] Tradier tick stream error: {e}")
                
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    if TRADIER_TOKEN:
        streamer = HarmonizedBotStreamer(TRADIER_TOKEN, TRADIER_BASE_URL)
        log_msg("[✓] Smart Tradier Market Streamer Initialized.")
        
        try:
            asyncio.run(streamer.start_tradier_stream(ACTIVE_TICKERS))
        except KeyboardInterrupt:
            log_msg("Streaming core terminated cleanly by operator.")
    else:
        log_msg("[!] Error: No Tradier token found inside .env file.")
