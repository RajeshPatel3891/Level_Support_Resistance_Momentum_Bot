import os
import sys
import json
import time
import argparse
import random
import csv
import ijson
from datetime import datetime

# Safe import wrapper to protect against module mismatches in test environments
try:
    import LiveBot
    from LiveBot import calculate_trade_conviction, calculate_exits
except ImportError:
    LiveBot = None
    def calculate_trade_conviction(*args, **kwargs):
        return {"conviction": "LOW", "action": "PASS", "notes": "Fallback import proxy active."}
    def calculate_exits(price):
        return (price - 0.50, price + 1.00, None)

# --- SYSTEM DIRECTORY RESOLUTION & CONFIGURATION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
LEVELS_FILE = os.path.join(PARENT_DIR, 'trading_levels.json')
MACRO_STATE_FILE = os.path.join(PARENT_DIR, 'macro_state.json')

# Expanded to natively include TSLA
from src.utils.universe import get_playbook_tickers
TICKERS = get_playbook_tickers()

class BacktestBot:
    def __init__(self, is_live=False, date="2026-07-07", max_risk=20.0):
        self.is_live = is_live
        self.target_date = date
        self.range_safeguard = 0.20
        self.levels_cache = {}
        self.active_positions = {}
        self.trade_history = []
        self.active_windows = {}
        self.printed_errors = set() 
        
        self.current_bar_state = {}
        self.sidekick_signals = {}
        
        self.last_trade_exit_tick = {}
        self.rolling_prices = {}  
        
        # --- DYNAMIC RISK PARAMETERS ---
        self.max_risk_dollars = max_risk 
        self.initial_capital = 10000.0
        self.current_cash = self.initial_capital
        
        self.load_levels()
        
        if self.is_live:
            print(f"[👁️] HARM.AI SHADOW PIPELINE: Live Auditor active... | Max Risk: ${self.max_risk_dollars:.2f}", flush=True)
        else:
            print(f"[⚙️] HARM.AI BACKTEST ENGINE: Offline Historical Simulator loaded. | Max Risk: ${self.max_risk_dollars:.2f}", flush=True)

    def load_levels(self):
        try:
            if os.path.exists(LEVELS_FILE):
                with open(LEVELS_FILE, "r") as f:
                    data = json.load(f)
                self.levels_cache = data.get("levels", {})
        except Exception as e:
            print(f"[!] Backtester failed to load levels: {e}", flush=True)

    def print_audit_report(self):
        """Prints a professional HARM.AI performance summary card."""
        net_profit = sum([t['profit'] for t in self.trade_history])
        print("\n" + "="*50, flush=True)
        print(" HARM.AI PORTFOLIO PERFORMANCE AUDIT REPORT ", flush=True)
        print("="*50, flush=True)
        print(f"Total Trades: {len(self.trade_history)}", flush=True)
        print(f"Net Profit/Loss: ${net_profit:+.2f}", flush=True)
        print("="*50 + "\n", flush=True)

    def process_sidekick_bar(self, ticker, close, volume):
        if ticker not in self.active_windows:
            self.active_windows[ticker] = []
            
        self.active_windows[ticker].append({"close": close, "volume": volume})
        if len(self.active_windows[ticker]) > 5:
            self.active_windows[ticker].pop(0)
            
        if len(self.active_windows[ticker]) < 2:
            return
            
        prev_candle = self.active_windows[ticker][-2]
        prev_v = prev_candle["volume"]
        prev_close = prev_candle["close"]
        
        if prev_v > 0 and (volume / prev_v) >= 2.5:
            swing_low = prev_close
            swing_high = close
            wave_distance = swing_high - swing_low
            
            if wave_distance >= self.range_safeguard:
                fib_entry = swing_high - (0.382 * wave_distance)
                fib_target = swing_high + (0.272 * wave_distance)
                
                self.sidekick_signals[ticker] = {
                    "entry_limit": round(fib_entry, 2),
                    "target_tp": round(fib_target, 2),
                    "stop_loss": round(fib_entry - (wave_distance * 0.382), 2),
                    "active": True
                }

    def run_historical_tick_backtest(self, ticker):
        data_file = f"{ticker}_{self.target_date}.json"
        if not os.path.exists(data_file): return
            
        print(f"Executing Simulated Trade Audit for {ticker} on {self.target_date}...", flush=True)
        
        last_conviction = None
        in_trade = False
        trade_exit_levels = {} 
        audit_file = f"{ticker}_SIM_audit.csv"
        
        tactical = self.levels_cache.get(ticker, {}).get("human_tactical", {})
        breakout_val = tactical.get("breakout_trigger")
        reversal_zone = tactical.get("reversal_zone")
        
        low_z, high_z = None, None
        if isinstance(reversal_zone, list) and len(reversal_zone) >= 2:
            low_z, high_z = min(reversal_zone), max(reversal_zone)
        
        contracts = 5
        allocation_cost = contracts * 100.0
        entry_price = 0.0
        prev_price = None
        
        tick_idx = 0
        cooldown_until_idx = 0
        MIN_COOLDOWN_TICKS = 600
        
        with open(data_file, 'rb') as f, open(audit_file, "w", newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Timestamp", "Price", "Action", "Conviction", "Result", "Notes"])
            
            try:
                parser = ijson.items(f, 'item')
                for tick in parser:
                    price = float(tick.get('price'))
                    vol = float(tick.get('size', 0))
                    tick_time_str = tick.get('time')
                    tick_idx += 1
                    
                    if tick_time_str and len(tick_time_str) >= 16:
                        minute_key = tick_time_str[:16]
                        if ticker not in self.current_bar_state:
                            self.current_bar_state[ticker] = {"minute": minute_key, "close": price, "volume": 0.0}
                        if self.current_bar_state[ticker]["minute"] != minute_key:
                            self.process_sidekick_bar(ticker, self.current_bar_state[ticker]["close"], self.current_bar_state[ticker]["volume"])
                            self.current_bar_state[ticker] = {"minute": minute_key, "close": price, "volume": 0.0}
                        self.current_bar_state[ticker]["close"] = price
                        self.current_bar_state[ticker]["volume"] += vol

                    if prev_price is None: prev_price = price
                    
                    # Core Bot Decision Logic
                    conv = calculate_trade_conviction(ticker, price, "LONG", vol)
                    curr = conv.get("conviction")
                    
                    if in_trade:
                        if price <= trade_exit_levels['sl']:
                            net_loss = -abs(allocation_cost * ((entry_price - price) / entry_price) * 10.0)
                            self.trade_history.append({"profit": net_loss, "outcome": "STOP_LOSS"})
                            writer.writerow([tick_time_str, price, "EXIT", curr, "STOP_LOSS", ""])
                            in_trade = False
                        elif price >= trade_exit_levels['tp']:
                            net_gain = allocation_cost * ((price - entry_price) / entry_price) * 10.0
                            self.trade_history.append({"profit": net_gain, "outcome": "TAKE_PROFIT"})
                            writer.writerow([tick_time_str, price, "EXIT", curr, "TAKE_PROFIT", ""])
                            in_trade = False
                    else:
                        sidekick = self.sidekick_signals.get(ticker)
                        is_sidekick_fill = (sidekick and sidekick.get("active") and price <= sidekick["entry_limit"])
                        
                        # UPDATED TRIGGER LOGIC: Aggressive Scalp
                        is_breakout = breakout_val and (prev_price < breakout_val <= price)
                        is_reversal = low_z and high_z and (low_z <= price <= high_z) and (vol >= 500)
                        
                        if is_sidekick_fill or (curr == "HIGH" and last_conviction != "HIGH") or is_breakout or is_reversal:
                            if tick_idx >= cooldown_until_idx:
                                # Margin Bypass
                                if False: 
                                    pass
                                else:
                                    entry_price = price
                                    sl, tp = price - 0.50, price + 1.00
                                    trade_exit_levels = {'sl': sl, 'tp': tp}
                                    in_trade = True
                                    writer.writerow([tick_time_str, price, "ENTER", curr, "OPEN_TRADE", "Triggered"])
                    
                    last_conviction = curr
                    prev_price = price
            except Exception as e:
                pass
    
    def run_live_shadow_listener(self):
        for line in sys.stdin:
            if "BAR_TICK_DATA" in line:
                try:
                    data = json.loads(line.split("BAR_TICK_DATA:")[-1].strip())
                    self.process_historical_bar(data["symbol"], data["close"], data["volume"])
                except Exception: pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2026-07-07")
    args = parser.parse_args()
    
    bot = BacktestBot(date=args.date)
    for ticker in TICKERS:
        bot.run_historical_tick_backtest(ticker)
    bot.print_audit_report()
