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
        try:
            import sqlite3
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT ticker, spot_price, stop_loss, take_profit, timestamp FROM trades WHERE exit_status = 'ACTIVE' OR exit_status = 'SIM_TRAILING_STOP'")
            for row in cursor.fetchall():
                self.active_positions[row[0]] = {"entry_price": row[1], "stop_loss": row[2], "take_profit": row[3], "timestamp": row[4]}
            conn.close()
        except Exception as e: print(f"[!] Recovery Error: {e}")
        self.load_tactical_levels()
        print("[✓] HARM.AI Sidekick Engine: Production-Grade Orchestrator Loaded with CSO Context.")

    def load_tactical_levels(self):
        try:
            if os.path.exists(LEVELS_FILE):
                mtime = os.path.getmtime(LEVELS_FILE)
                if mtime > self.last_levels_mtime:
                    with open(LEVELS_FILE, "r") as f:
                        self.levels_cache = json.load(f)
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

            # Fallback cleanly to flat schema parameters
            support_val = float(self.levels_cache.get(symbol, {}).get("support_a", entry))

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
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                # Calculate basic percentage return
                pnl_pct = round(((current_close - pos["entry_price"]) / pos["entry_price"]) * 100, 7)
                cursor.execute("UPDATE trades SET spot_price = ?, net_pnl = ? WHERE ticker = ? AND timestamp = ?", (current_close, pnl_pct, symbol, pos["timestamp"]))
                conn.commit(); conn.close()
            except Exception as e: print(f"[!] Real-time Update Error: {e}")
            # Initialize trailing stop if not present
            if 'highest_price' not in pos or current_close > pos['highest_price']:
                pos['highest_price'] = max(current_close, pos.get('entry_price', current_close))
            
            # Dynamically calculate trailing stop floor (e.g., 1.5 * ATR below highest price reached)
            atr = pos.get('daily_atr', 1.5)
            dynamic_stop = max(pos['stop_loss'], pos['highest_price'] - (1.5 * atr))
            
            # Check exit triggers
            hit_tp = current_close >= pos['take_profit']
            hit_sl = current_close <= dynamic_stop
            
            if hit_tp or hit_sl:
                # Calculate exact dynamic shares based on $85 risk rules
                risk_dist = abs(pos['entry_price'] - pos['stop_loss'])
                shares = 85.0 / risk_dist if risk_dist > 0 else 1.0
                net_pnl = round((current_close - pos['entry_price']) * shares, 2)
                
                # Safeguard: cap loss at -$85 if slippage occurs
                if hit_sl and net_pnl < -85.0:
                    net_pnl = -85.00
                try:
                    conn = sqlite3.connect(DB_FILE)
                    cursor = conn.cursor()
                    cursor.execute("UPDATE trades SET exit_price = ?, exit_status = ?, net_pnl = ? WHERE ticker = ? AND exit_status = 'ACTIVE'", 
                                   (current_close, "TAKE_PROFIT" if hit_tp else ("TRAILING_STOP" if dynamic_stop > pos['stop_loss'] else "STOP_LOSS"), round(net_pnl, 2), symbol))
                    conn.commit(); conn.close()
                    print(f"[!] Exit Triggered for {symbol}: ${net_pnl}")
                except Exception as e: 
                    print(f"[!] DB Exit Error: {e}")
                finally:
                    if symbol in self.active_positions:
                        del self.active_positions[symbol]
        
        # Signal Engine
        if symbol in self.levels_cache and symbol not in self.active_positions:
            tactical = self.levels_cache[symbol].get("human_tactical", {})
            trigger = self.levels_cache[symbol].get("support_a")
            atr = self.levels_cache[symbol].get("daily_atr", 1.5)
            if trigger and current_close >= trigger:
                override, _, _, _, _, _, _ = self.get_macro_safety_state()
                if not override:
                    self.inject_active_position(symbol, "CALL", current_close, round(current_close - (atr * 0.5), 2), round(current_close + (atr * 1.5), 2), "BREAKOUT")

def stream_output(process, sidekick):
    # Use readlines to avoid locking resources during stream termination
    for line in iter(process.stdout.readline, ''):
        if not line:
            break
        if "BAR_TICK_DATA" in line:
            print(f"[SENTRY_LOG] {line.strip()}", flush=True)
            try:
                data = json.loads(line.split("BAR_TICK_DATA:")[-1].strip())
                sidekick.process_live_candle(data["symbol"], data["close"], data["volume"])
            except: pass

def force_kill_subprocesses(signum=None, frame=None):
    """Clean exit handler that forcefully reaps subprocesses."""
    print("\n🛑 [SHUTDOWN] Intercepted termination signal. Reaping engines...")
    global live_bot, shadow_bot
    for label, proc in [("Live Bot", live_bot), ("Shadow Bot", shadow_bot)]:
        if proc and proc.poll() is None:
            print(f" └─ Sending SIGTERM to {label}...")
            proc.terminate()
            try:
                # Wait up to 1 second for graceful exit
                proc.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                print(f" └─ [⚠️ FORCE] {label} refused to exit. Sending SIGKILL...")
                proc.kill()
                proc.wait()
    print("[✓] Process ecosystem cleared. Exiting safely.\n")
    sys.exit(0)

if __name__ == "__main__":
    # Register handlers supporting standard signal interface arguments
    signal.signal(signal.SIGINT, force_kill_subprocesses)
    signal.signal(signal.SIGTERM, force_kill_subprocesses)
    
    sidekick = MicroScalpSidekick()
    live_bot = subprocess.Popen([sys.executable, "-u", "src/AlpacaPipeline.py"], stdout=subprocess.PIPE, text=True)
    shadow_bot = subprocess.Popen([sys.executable, "-u", "src/BacktestBot.py", "--live"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    
    threading.Thread(target=stream_output, args=(live_bot, sidekick), daemon=True).start()
    threading.Thread(target=stream_output, args=(shadow_bot, sidekick), daemon=True).start()
    
    print("[✓] Process Supervisor active. Monitoring engines persistently...", flush=True)
    try:
        while True:
            time.sleep(5)
            # If a process finished, don't let MasterSentry exit!
            if live_bot.poll() is not None:
                # Optional: Add auto-restart logic here if needed
                pass
    except (KeyboardInterrupt, SystemExit):
        force_kill_subprocesses()
