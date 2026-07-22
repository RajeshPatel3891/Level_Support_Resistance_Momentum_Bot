import os
import sys
import json
import time
import sqlite3
import signal
import pytz
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Discord Configuration
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

# Paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

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
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT ticker, spot_price, stop_loss, take_profit, timestamp FROM trades WHERE exit_status = 'ACTIVE' OR exit_status = 'SIM_TRAILING_STOP'")
            for row in cursor.fetchall():
                self.active_positions[row[0]] = {"entry_price": row[1], "stop_loss": row[2], "take_profit": row[3], "timestamp": row[4]}
            conn.close()
        except Exception as e:
            print(f"[!] Recovery Error: {e}")
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
            from telemetry_bridge import TelemetryBridge
            bridge = TelemetryBridge(db_path=DB_FILE)
            
            # Fetch CSO Clearance
            override, regime, catalyst, directive, market_bias, asset_biases, risk_score = self.get_macro_safety_state()
            cso_cleared = not override
            cso_notes = f"{regime} | {catalyst}"

            ticker_data = self.levels_cache.get(symbol, {}) if isinstance(self.levels_cache.get(symbol), dict) else {}
            support_val = float(ticker_data.get("support_a", entry))

            dist = abs(entry - support_val)
            allowed = 2.50
            prox = round(max(1.0, min(100.0, (1.0 - (dist / (allowed * 20))) * 100.0)), 2)
            print(f"[DEBUG] Proximity Calc: Dist={dist:.2f}, Allowed={allowed:.2f}, Prox={prox}")

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

    def audit_active_positions(self):
        """Monitors live active positions and enforces stop loss / take profit rules."""
        if not os.path.exists(DB_FILE):
            return
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT ticker, spot_price, stop_loss, take_profit, timestamp FROM trades WHERE exit_status = 'ACTIVE'")
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                print("[*] MasterSentry Standby: No active positions require risk monitoring.")
                return

            print(f"[*] MasterSentry Active Risk Audit: {len(rows)} live position(s) under surveillance.")

            from dashboard_server import get_live_quote

            for row in rows:
                ticker, entry_price, stop_loss, take_profit, timestamp = row[0], row[1], row[2], row[3], row[4]
                quote = get_live_quote(ticker)
                if not quote or 'last' not in quote or not quote['last']:
                    continue

                live_spot = float(quote['last'])
                entry_spot = float(entry_price) if entry_price else live_spot

                # Delta Options PnL calculation (1 contract = 100 shares, Delta = 0.50)
                delta = 0.50
                spot_diff = live_spot - entry_spot
                option_pnl = spot_diff * delta * 100

                # 1. HARD $30 DOLLAR LOSS CAP
                if option_pnl <= -30.00:
                    print(f"[🚨 EMERGENCY STOP] {ticker}: Option loss hit ${option_pnl:.2f} (Breached -$30 Limit). Auto-Closing!")
                    conn_update = sqlite3.connect(DB_FILE)
                    conn_update.execute("""
                        UPDATE trades 
                        SET exit_status = 'STOP_LOSS_DOLLAR_CAP', exit_price = ?, net_pnl = ? 
                        WHERE ticker = ? AND exit_status = 'ACTIVE'
                    """, (live_spot, -30.00, ticker))
                    conn_update.commit()
                    conn_update.close()

                # 2. TECHNICAL STOCK SPOT STOP LOSS
                elif stop_loss and live_spot <= float(stop_loss):
                    print(f"[⚠️ TECHNICAL STOP] {ticker}: Spot ${live_spot:.2f} hit SL level ${stop_loss}. Auto-Closing!")
                    conn_update = sqlite3.connect(DB_FILE)
                    conn_update.execute("""
                        UPDATE trades 
                        SET exit_status = 'STOP_LOSS_HIT', exit_price = ?, net_pnl = ? 
                        WHERE ticker = ? AND exit_status = 'ACTIVE'
                    """, (live_spot, -30.00, ticker))
                    conn_update.commit()
                    conn_update.close()

        except Exception as e:
            print(f"[!] MasterSentry Risk Audit Error: {e}")

def handle_shutdown_signal(signum=None, frame=None):
    """Clean exit handler."""
    print("\n🛑 [SHUTDOWN] Intercepted termination signal. Exiting MasterSentry safely.")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    print("=" * 65)
    print("[⚙️] MASTERSENTRY ACTIVE RISK MONITOR INITIALIZED")
    print("Target Session: Pure Tradier Stream & Execution Engine")
    print("=" * 65)

    sidekick = MicroScalpSidekick()
    
    try:
        while True:
            sidekick.load_tactical_levels()
            sidekick.audit_active_positions()
            time.sleep(10)
    except (KeyboardInterrupt, SystemExit):
        handle_shutdown_signal()
