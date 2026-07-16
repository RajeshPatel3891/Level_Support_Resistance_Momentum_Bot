import os
import sqlite3
from dotenv import load_dotenv; load_dotenv()
import subprocess
import sys
import threading
import time
import urllib.request
import json
import signal
from datetime import datetime

# Discord Configuration
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1516048864325537847/fiH0REc5aHygxCfHFmplUA1tJlVfRJOI4MBRG4Oe0Kf_M2cigVyP5oPLgQvY9JG3vKk4"

# Paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
MACRO_STATE_FILE = os.path.join(PARENT_DIR, 'macro_state.json')
LEVELS_FILE = os.path.join(PARENT_DIR, 'trading_levels.json')
DB_FILE = os.path.join(PARENT_DIR, 'harm_telemetry.db')

class MicroScalpSidekick:
    def __init__(self):
        self.active_windows = {} 
        self.levels_cache = {}
        self.last_levels_mtime = 0
        self.active_positions = {}
        self.load_tactical_levels()
        print("[✓] HARM.AI Sidekick Engine: Production-Grade Orchestrator Loaded with CSO Context.")

    def load_tactical_levels(self):
        try:
            if os.path.exists(LEVELS_FILE):
                mtime = os.path.getmtime(LEVELS_FILE)
                if mtime > self.last_levels_mtime:
                    with open(LEVELS_FILE, "r") as f:
                        self.levels_cache = json.load(f).get("levels", {})
                    self.last_levels_mtime = mtime
                    print("[⚙️] Sentry dynamically loaded levels.")
        except Exception as e:
            print(f"[!] Error loading levels: {e}")

    def get_macro_safety_state(self):
        """Returns the full 7-item CSO macro state for risk assessment."""
        try:
            if os.path.exists(MACRO_STATE_FILE):
                with open(MACRO_STATE_FILE, "r") as f:
                    state = json.load(f)
                return (
                    state.get("systemic_override", False),
                    state.get("macro_regime", "UNKNOWN"),
                    state.get("primary_catalyst", "No active catalyst"),
                    state.get("operational_directive", "Maintain standard parameters"),
                    state.get("market_bias", "NEUTRAL").upper(),
                    state.get("asset_biases", {}),
                    state.get("risk_score", 50)
                )
        except Exception as e:
            print(f"[!] Warning reading macro state in Sentry: {e}")
        return (False, "UNKNOWN", "Fallback Mode", "Unable to read macro state.", "NEUTRAL", {}, 50)

    def inject_active_position(self, symbol, direction, entry, sl, tp, strategy):
        """Injects active position into SQL with CSO clearance context."""
        try:
            if PARENT_DIR not in sys.path:
                sys.path.append(PARENT_DIR)
            from telemetry_bridge import TelemetryBridge
            bridge = TelemetryBridge(db_path=DB_FILE)
            
            # Fetch CSO Clearance
            override, regime, catalyst, directive, market_bias, asset_biases, risk_score = self.get_macro_safety_state()
            cso_cleared = not override
            cso_notes = f"{regime} | {catalyst}"

            support_val = float(self.levels_cache.get(symbol, {}).get("algo_macro", {}).get("support", [entry])[0])
            if support_val == 0: support_val = entry
            if symbol in self.levels_cache:
                support_list = self.levels_cache[symbol].get("algo_macro", {}).get("support", [])
                if support_list:
                    support_val = float(support_list[0])

            dist = abs(entry - support_val)
            allowed = 2.50
            prox = round(max(1.0, min(100.0, (1.0 - (dist / (allowed * 20))) * 100.0)), 2)
            print(f"[DEBUG] Proximity Calc: Dist={dist:.2f}, Allowed={allowed:.2f}, Prox={prox}")
            allowed = 2.50

            ts_entry = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            bridge.log_trade(
                ticker=symbol,
                strategy=strategy,
                direction=direction,
                support_level=support_val,
                spot_price=entry,
                stop_loss=sl,
                take_profit=tp,
                distance=dist,
                allowed_dist=allowed,
                proximity_score=prox,
                exit_status="ACTIVE",
                net_pnl=0.0,
                is_live=True,
                cso_cleared=cso_cleared,
                cso_notes=cso_notes
            )
            
            self.active_positions[symbol] = {
                "strategy": strategy,
                "direction": direction,
                "entry_price": entry,
                "stop_loss": sl,
                "take_profit": tp,
                "timestamp": ts_entry
            }
            print(f"[✓] TelemetryBridge: {symbol} logged at ${entry} (CSO Cleared: {cso_cleared})")
        except Exception as e:
            print(f"[!] Critical SQL Write Error: {e}")

    def process_live_candle(self, symbol, current_close, current_volume):
        # Exit Monitoring
        if symbol in self.active_positions:
            pos = self.active_positions[symbol]
            if current_close <= pos['stop_loss'] or current_close >= pos['take_profit']:
                net_pnl = 500.0 if current_close >= pos['take_profit'] else -500.0
                try:
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE trades SET exit_price = ?, exit_status = ?, net_pnl = ? WHERE ticker = ? AND timestamp = ? AND exit_status = 'ACTIVE' AND is_live = 1", 
                                   (current_close, "STOP_LOSS" if current_close <= pos['stop_loss'] else "TAKE_PROFIT", round(net_pnl, 2), symbol, pos['timestamp']))
                    conn.commit(); conn.close()
                    del self.active_positions[symbol]
                    print(f"[!] Exit Triggered for {symbol}: ${net_pnl}")
                except Exception as e: print(f"[!] DB Exit Error: {e}")
        
        # Signal Engine
        if symbol in self.levels_cache:
            tactical = self.levels_cache[symbol].get("human_tactical", {})
            trigger = tactical.get("breakout_trigger")
            if trigger and current_close >= trigger:
                override, _, _, _, _, _, _ = self.get_macro_safety_state()
                if not override:
                    self.inject_active_position(symbol, "CALL", current_close, round(current_close-1.5,2), round(current_close+3.0,2), "BREAKOUT")

def stream_output(process, sidekick):
    for line in iter(process.stdout.readline, ''):
        if "BAR_TICK_DATA" in line:
            try:
                data = json.loads(line.split("BAR_TICK_DATA:")[-1].strip())
                sidekick.process_live_candle(data["symbol"], data["close"], data["volume"])
            except: pass

def force_kill_subprocesses():
    global live_bot, shadow_bot
    for proc in [live_bot, shadow_bot]:
        if proc and proc.poll() is None: proc.terminate()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, force_kill_subprocesses)
    sidekick = MicroScalpSidekick()
    live_bot = subprocess.Popen([sys.executable, "-u", "src/AlpacaPipeline.py"], stdout=subprocess.PIPE, text=True)
    shadow_bot = subprocess.Popen([sys.executable, "-u", "src/BacktestBot.py", "--live"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    threading.Thread(target=stream_output, args=(live_bot, sidekick), daemon=True).start()
    threading.Thread(target=stream_output, args=(shadow_bot, sidekick), daemon=True).start()
    try:
        while True: time.sleep(1)
    except: force_kill_subprocesses()
