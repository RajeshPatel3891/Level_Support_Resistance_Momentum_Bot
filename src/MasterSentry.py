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

# Import Gemini CSO Evaluator
try:
    from src.gemini_cso_evaluator import evaluate_macro_rebound
except ImportError:
    try:
        from gemini_cso_evaluator import evaluate_macro_rebound
    except ImportError:
        evaluate_macro_rebound = None

class MicroScalpSidekick:
    def __init__(self):
        self.active_windows = {} 
        self.levels_cache = {}
        self.last_levels_mtime = 0
        self.active_positions = {}
        self.cso_cooldowns = {}  # Suppresses repeat Gemini API calls (ticker: timestamp)

        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT ticker, spot_price, stop_loss, take_profit, timestamp, entry_price, shares FROM trades WHERE exit_status = 'ACTIVE' OR exit_status = 'SIM_TRAILING_STOP'")
            for row in cursor.fetchall():
                self.active_positions[row[0]] = {"entry_price": row[1], "stop_loss": row[2], "take_profit": row[3], "timestamp": row[4]}
            conn.close()
        except Exception as e:
            print(f"[!] Recovery Error: {e}")

        self.load_tactical_levels()
        print("[✓] HARM.AI Sidekick Engine: Production-Grade Orchestrator Loaded with Dual-Stage CSO Context.")

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
        """Monitors live active positions with Dual-Stage ATR + Gemini CSO risk rules."""
        if not os.path.exists(DB_FILE):
            return
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT ticker, spot_price, stop_loss, take_profit, timestamp, entry_price, shares FROM trades WHERE exit_status = 'ACTIVE'")
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                print("[*] MasterSentry Standby: No active positions require risk monitoring.")
                return

            print(f"[*] MasterSentry Active Risk Audit: {len(rows)} live position(s) under surveillance.")

            from dashboard_server import get_live_quote

            for row in rows:
                ticker = row[0]
                entry_price = float(row[1]) if row[1] else 0.0
                stop_loss = row[2]
                take_profit = row[3]

                quote = get_live_quote(ticker)
                if not quote or 'last' not in quote or not quote['last']:
                    continue

                live_spot = float(quote['last'])
                if entry_price == 0.0:
                    entry_price = live_spot

                # Option pricing estimation (Delta = 0.50, 1 contract = $100 per $1 spot move)
                delta = 0.50
                spot_diff = live_spot - entry_price
                shares_cnt = float(row[7]) if (len(row) > 7 and row[7]) else 1.0
                option_pnl = spot_diff * delta * 100.0 * shares_cnt

                # Estimated Contract Basis ($250 per contract baseline if unavailable)
                estimated_basis = max(30.0, entry_price * 100.0 * shares_cnt)
                pnl_pct = option_pnl / estimated_basis

                # Dynamic ATR Loss Threshold Calculation
                ticker_data = self.levels_cache.get(ticker, {}) if isinstance(self.levels_cache.get(ticker), dict) else {}
                atr_14 = float(ticker_data.get("atr", live_spot * 0.035))  # Default to 3.5% ATR if unlisted
                atr_pct = atr_14 / live_spot
                
                # Scale ATR Hard Stop % (Min 20% for low beta, Max 42% for high beta)
                max_loss_pct = max(0.20, min(0.42, atr_pct * 10.0))
                hard_stop_dollars = -1.0 * (estimated_basis * max_loss_pct)

                # STAGE 1: DYNAMIC ATR HARD STOP BREACHED
                if option_pnl <= hard_stop_dollars:
                    print(f"[🚨 EMERGENCY ATR HARD STOP] {ticker}: Option loss ${option_pnl:.2f} reached ATR limit ${hard_stop_dollars:.2f} ({pnl_pct*100:.1f}%). Auto-Closing!")
                    conn_update = sqlite3.connect(DB_FILE)
                    conn_update.execute("""
                        UPDATE trades 
                        SET exit_status = 'STOP_LOSS_ATR_HARD_CAP', exit_price = ?, net_pnl = ? 
                        WHERE ticker = ? AND exit_status = 'ACTIVE'
                    """, (live_spot, option_pnl, ticker))
                    conn_update.commit()
                    conn_update.close()
                    continue

                # STAGE 2: SOFT STOP (-20%) -> GEMINI CSO EVALUATION
                elif pnl_pct <= -0.20 and evaluate_macro_rebound is not None:
                    now_ts = time.time()
                    last_cso_call = self.cso_cooldowns.get(ticker, 0)

                    # 3-Minute Cooldown window per ticker
                    if now_ts - last_cso_call > 180:
                        self.cso_cooldowns[ticker] = now_ts
                        print(f"[🧠 CSO ESCALATION] {ticker} hit -20% soft stop ({pnl_pct*100:.1f}%). Requesting Gemini CSO Evaluation...")

                        override, regime, catalyst, directive, market_bias, asset_biases, risk_score = self.get_macro_safety_state()
                        
                        telemetry_payload = {
                            "ticker": ticker,
                            "entry_premium": estimated_basis / 100.0,
                            "current_premium": (estimated_basis + option_pnl) / 100.0,
                            "drawdown_pct": pnl_pct * 100.0,
                            "spot_price": live_spot,
                            "vwap": float(ticker_data.get("vwap", live_spot)),
                            "support_zone": str(ticker_data.get("support_a", "N/A")),
                            "resistance_zone": str(ticker_data.get("resistance_a", "N/A")),
                            "market_trend": f"Regime: {regime} | Market Bias: {market_bias}"
                        }

                        cso_verdict = evaluate_macro_rebound(telemetry_payload)
                        verdict = cso_verdict.get("verdict", "HOLD_REBOUND")
                        reasoning = cso_verdict.get("reasoning", "No reasoning provided.")

                        if verdict == "CUT_EARLY":
                            print(f"[🛑 CSO MACRO CUT] {ticker}: Gemini CSO advised CUT_EARLY. Rationale: {reasoning}")
                            conn_update = sqlite3.connect(DB_FILE)
                            conn_update.execute("""
                                UPDATE trades 
                                SET exit_status = 'CSO_MACRO_CUT', exit_price = ?, net_pnl = ? 
                                WHERE ticker = ? AND exit_status = 'ACTIVE'
                            """, (live_spot, option_pnl, ticker))
                            conn_update.commit()
                            conn_update.close()
                            continue
                        else:
                            print(f"[🟢 CSO HOLD REBOUND] {ticker}: Gemini CSO advised HOLD_REBOUND. Rationale: {reasoning}")

                # STAGE 4: DYNAMIC SCALED SCALE-OUT (TRIM 50% + TRAIL RUNNER)
                # Dynamic Capital-Proportional Trim Check (+15% ROI on total entry outlay)
                elif pnl_pct >= 0.15 or option_pnl >= max(30.0, (contract_cost_total if "contract_cost_total" in locals() else entry_price * shares_cnt * 100) * 0.15):
                    conn_update = sqlite3.connect(DB_FILE)
                    cursor_u = conn_update.cursor()
                    cursor_u.execute("SELECT shares FROM trades WHERE ticker = ? AND exit_status = 'ACTIVE'", (ticker,))
                    row_s = cursor_u.fetchone()
                    curr_shares = row_s[0] if row_s else 1.0
                    
                    if curr_shares > 1.0:
                        trim_shares = round(curr_shares / 2.0, 1)
                        remain_shares = curr_shares - trim_shares
                        print(f"[💰 SCALED TRIM EXECUTED] {ticker}: Trimming {trim_shares} contracts. Holding {remain_shares} runner contracts.")
                        cursor_u.execute("""
                            UPDATE trades 
                            SET shares = ?, stop_loss = ?, exit_status = 'SIM_TRAILING_STOP'
                            WHERE ticker = ? AND exit_status = 'ACTIVE'
                        """, (remain_shares, live_spot - 0.50, ticker))
                    else:
                        print(f"[🏁 FULL EXIT EXECUTED] {ticker}: Closing position at ${live_spot}.")
                        cursor_u.execute("""
                            UPDATE trades 
                            SET exit_status = 'TAKE_PROFIT_ROI', exit_price = ?, net_pnl = ? 
                            WHERE ticker = ? AND exit_status IN ('ACTIVE', 'SIM_TRAILING_STOP')
                        """, (live_spot, option_pnl, ticker))
                    conn_update.commit()
                    conn_update.close()
                    continue

                # STAGE 3: TECHNICAL SPOT STOP LOSS
                elif stop_loss and live_spot <= float(stop_loss):
                    print(f"[⚠️ TECHNICAL STOP] {ticker}: Spot ${live_spot:.2f} hit SL level ${stop_loss}. Auto-Closing!")
                    conn_update = sqlite3.connect(DB_FILE)
                    conn_update.execute("""
                        UPDATE trades 
                        SET exit_status = 'STOP_LOSS_HIT', exit_price = ?, net_pnl = ? 
                        WHERE ticker = ? AND exit_status = 'ACTIVE'
                    """, (live_spot, option_pnl, ticker))
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
    print("Target Session: Pure Tradier Stream & Gemini CSO Risk Engine")
    print("=" * 65)

    sidekick = MicroScalpSidekick()
    
    try:
        while True:
            sidekick.load_tactical_levels()
            sidekick.audit_active_positions()
            time.sleep(10)
    except (KeyboardInterrupt, SystemExit):
        handle_shutdown_signal()
