import os
import sys
import json
import sqlite3
import asyncio
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TRADIER_TOKEN = os.getenv("TRADIER_TOKEN") or os.getenv("TRADIER_SANDBOX_TOKEN")
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")
ACTIVE_TICKERS = [t.strip() for t in os.getenv("ACTIVE_TICKERS", "SPY,QQQ,IWM,NVDA,TSLA,AAPL,AMZN,GOOGL,AMD,META,NFLX,PLTR,HOOD,SOFI,F,AAL,RIVN,BAC,SNAP,MARA,CCL,UBER,NKE,INTC").split(",") if t.strip()]

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
        self.active_tickers = list(ACTIVE_TICKERS)
        self.active_monitors = {}
        self.init_database()
        self.sync_active_positions_from_db()

    def init_database(self):
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
                spot_price REAL,
                exit_price REAL,
                stop_loss REAL,
                take_profit REAL,
                distance REAL,
                allowed_dist REAL,
                proximity_score REAL,
                exit_status TEXT,
                net_pnl REAL
            )
        """)
        conn.commit()
        conn.close()
        log_msg("[✓] Trade telemetry database verified and active.")

    def sync_active_positions_from_db(self):
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
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
            shares = abs(float(row["shares"])) if ("shares" in keys and row["shares"]) else 1.0
            entry_p = float(row["entry_price"] or row["spot_price"] or 0.0)
            
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

    def update_dashboard_data_json(self, quotes_dict):
        try:
            active_positions_list = []
            
            for ticker, positions in self.active_monitors.items():
                underlying_data = quotes_dict.get(ticker, {})
                spot_price = underlying_data.get("last", 0.0)
                
                for pos in positions:
                    occ = pos["occ_symbol"]
                    entry_p = pos["entry_price"]
                    shares = pos["shares"]
                    direction = pos["direction"]
                    strategy = pos["strategy"]
                    sl = pos["stop_loss"]
                    tp = pos["take_profit"]
                    
                    option_data = quotes_dict.get(occ, {})
                    opt_bid = float(option_data.get("bid", 0.0) or 0.0)
                    opt_ask = float(option_data.get("ask", 0.0) or 0.0)
                    opt_last = float(option_data.get("last", 0.0) or 0.0)
                    
                    if opt_bid > 0 and opt_ask > 0:
                        cur_price = round((opt_bid + opt_ask) / 2.0, 2)
                    elif opt_last > 0:
                        cur_price = opt_last
                    else:
                        cur_price = entry_p

                    pnl_per_contract = (cur_price - entry_p) * 100.0
                    total_pnl = round(pnl_per_contract * shares, 2)
                    pnl_pct = round(((cur_price - entry_p) / entry_p) * 100.0, 2) if entry_p > 0 else 0.0
                    
                    spread = opt_ask - opt_bid
                    fill_score = 10.0
                    if spread > 0 and entry_p > 0:
                        fill_score = round(max(0.0, min(10.0, ((opt_ask - entry_p) / spread) * 10.0)), 1)
                    
                    bid_display = f"{opt_bid:.2f}" if opt_bid > 0 else f"{entry_p:.2f}"
                    ask_display = f"{opt_ask:.2f}" if opt_ask > 0 else f"{entry_p:.2f}"
                    pnl_str = f"{total_pnl:+.2f}"

                    active_positions_list.append({
                        "id": pos["db_id"],
                        "ticker": ticker,
                        "occ_symbol": occ,
                        "direction": direction,
                        "strategy": strategy,
                        "entry_price": f"{entry_p:.2f}",
                        "current_price": f"{cur_price:.2f}",
                        "current_bid": bid_display,
                        "current_ask": ask_display,
                        "bid": bid_display,
                        "ask": ask_display,
                        "spot_price": spot_price,
                        "shares": shares,
                        "stop_loss": f"{sl:.2f}",
                        "take_profit": f"{tp:.2f}",
                        "pnl_dollars": pnl_str,
                        "dollar_pnl": pnl_str,
                        "net_pnl": total_pnl,
                        "pnl_pct": f"{pnl_pct:+.1f}",
                        "fill_quality_score": f"{fill_score:.1f}",
                        "confidence_status": "HIGH",
                        "confidence_score": "HIGH",
                        "status": "ACTIVE"
                    })

            payload = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "quotes": quotes_dict,
                "active_positions": active_positions_list,
                "active_trade_cards": active_positions_list
            }

            temp_json = f"{DATA_JSON}.tmp"
            with open(temp_json, 'w') as f:
                json.dump(payload, f, indent=2)
            os.replace(temp_json, DATA_JSON)
        except Exception as e:
            log_msg(f"[!] Error updating dashboard_data.json: {e}")

    def fetch_tradier_quotes(self, symbols_list):
        if not symbols_list:
            return {}
        symbols = ",".join(list(set(symbols_list)))
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
                
                result = {}
                for q in quotes:
                    if q and "symbol" in q:
                        sym = q["symbol"]
                        last_px = float(q.get("last") or 0.0)
                        bid_px = float(q.get("bid") or 0.0)
                        ask_px = float(q.get("ask") or 0.0)
                        vwap_px = float(q.get("vwap") or last_px)
                        
                        result[sym] = {
                            "last": last_px,
                            "bid": bid_px,
                            "ask": ask_px,
                            "vwap": vwap_px
                        }
                return result
        except Exception as e:
            log_msg(f"[!] Error fetching Tradier quotes: {e}")
        return {}

    async def start_tradier_stream(self, tickers=None):
        base_watch_list = list(tickers or self.active_tickers)
        log_msg(f"Initiating Quote Streamer & Dashboard Telemetry Feed: {base_watch_list}")

        while True:
            try:
                self.sync_active_positions_from_db()
                
                active_symbols = list(base_watch_list)
                for ticker, positions in self.active_monitors.items():
                    if ticker not in active_symbols:
                        active_symbols.append(ticker)
                    for pos in positions:
                        occ = pos.get("occ_symbol")
                        if occ and occ not in active_symbols:
                            active_symbols.append(occ)

                quotes = self.fetch_tradier_quotes(active_symbols)
                if quotes:
                    spot_dict = {t: q["last"] for t, q in quotes.items() if len(t) <= 6}
                    self.update_levels_file_spot_prices(spot_dict)
                    self.update_dashboard_data_json(quotes)
                
            except Exception as e:
                log_msg(f"[─] Tradier tick stream error: {e}")
                
            await asyncio.sleep(1.0)

if __name__ == "__main__":
    if TRADIER_TOKEN:
        streamer = HarmonizedBotStreamer(TRADIER_TOKEN, TRADIER_BASE_URL)
        log_msg("[✓] Smart Tradier Market Streamer & Dashboard Feed Initialized.")
        
        try:
            asyncio.run(streamer.start_tradier_stream(ACTIVE_TICKERS))
        except KeyboardInterrupt:
            log_msg("Streaming core terminated cleanly by operator.")
    else:
        log_msg("[!] Error: No Tradier token found inside .env file.")
