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

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(CURRENT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

MACRO_STATE_FILE = os.path.join(PARENT_DIR, 'macro_state.json')
LEVELS_FILE = os.path.join(PARENT_DIR, 'trading_levels.json')
DB_FILE = os.path.join(PARENT_DIR, 'harm_telemetry.db')

from src.RiskEngine import (
    calculate_gex_hit_probability,
    resolve_direction_targets,
    evaluate_cso_informed_exit
)

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
        self.cso_cooldowns = {} 
        self.cso_ev_state_cache = {} # State Transition Cache (ticker: {"state": str, "last_ping": float})

        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT ticker, spot_price, stop_loss, take_profit, timestamp, entry_price, shares, direction, id FROM trades WHERE exit_status = 'ACTIVE' OR exit_status = 'SIM_TRAILING_STOP'")
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

    def process_cso_ev_guard(self, trade_id: int, ticker: str, live_spot: float, stop_loss_val: float, direction: str, shares_cnt: float, option_pnl: float):
        """State Transition Guard for CSO Expected Value (EV) exits."""
        gex_target, stop_loss_val, gex_label = resolve_direction_targets(ticker, live_spot, direction, stop_loss_val)
        
        if not gex_target:
            return

        hit_prob = calculate_gex_hit_probability(live_spot, gex_target, gex_label)
        cso_eval = evaluate_cso_informed_exit(live_spot, gex_target, stop_loss_val, hit_prob, option_pnl, shares_cnt)
        recommendation = cso_eval["recommendation"]

        now_ts = time.time()
        cached = self.cso_ev_state_cache.get(ticker, {"state": "HOLD", "last_ping": 0})
        
        state_changed = (recommendation != cached["state"])
        time_elapsed = now_ts - cached["last_ping"]

        if recommendation in ["TAKE_PROFIT_NOW", "TIGHTEN_STOP"]:
            if state_changed or time_elapsed >= 120:
                print(f"[🧠 CSO EV ALERT] {ticker} -> Recommendation: {recommendation} | Reason: {cso_eval['reason']}")
                self.cso_ev_state_cache[ticker] = {"state": recommendation, "last_ping": now_ts}

                if recommendation == "TAKE_PROFIT_NOW":
                    print(f"[🎯 CSO AUTO-LOCK GAINS] Closing {ticker} to secure ${option_pnl:+.2f} profit!")
                    with sqlite3.connect(DB_FILE, timeout=30.0) as conn_u:
                        conn_u.execute('PRAGMA busy_timeout = 30000;')
                        conn_u.execute('PRAGMA journal_mode = WAL;')
                        conn_u.execute("""
                            UPDATE trades 
                            SET exit_status = 'CSO_TAKE_PROFIT_LOCK', exit_price = CASE WHEN entry_price < 50.0 THEN round(entry_price + (spot_diff * 0.5), 2) ELSE ? END + (? * 0.0001), net_pnl = ?, cso_notes = ?
                            WHERE id = ? AND exit_status = 'ACTIVE'
                        """, (live_spot, trade_id, option_pnl, f"Reason: {cso_eval['reason']}", trade_id))
                        conn_u.commit()

    def audit_active_positions(self):
        if not os.path.exists(DB_FILE):
            return
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("SELECT ticker, spot_price, stop_loss, take_profit, timestamp, entry_price, shares, direction, id FROM trades WHERE exit_status = 'ACTIVE'")
            rows = cursor.fetchall()
            conn.close()

            if not rows:
                return

            from dashboard_server import get_live_quote

            for row in rows:
                ticker = row[0]
                spot_price = row[1]
                stop_loss = row[2]
                take_profit = row[3]
                timestamp = row[4]
                entry_price = float(row[5]) if (len(row) > 5 and row[5] is not None) else (float(row[1]) if row[1] else 0.0)
                shares_cnt = float(row[6]) if (len(row) > 6 and row[6]) else 1.0
                direction = row[7] if (len(row) > 7 and row[7]) else 'CALL'
                trade_id = row[8]

                quote = get_live_quote(ticker)
                if not quote or 'last' not in quote or not quote['last']:
                    continue

                live_spot = float(quote['last'])
                if entry_price == 0.0:
                    entry_price = live_spot

                delta = 0.50
                spot_diff = live_spot - entry_price if str(direction).upper() == 'CALL' else entry_price - live_spot
                option_pnl = spot_diff * delta * 100.0 * shares_cnt

                estimated_basis = max(30.0, entry_price * 100.0 * shares_cnt)
                pnl_pct = option_pnl / estimated_basis

                # 1. Process CSO Expected Value Exit Guard
                self.process_cso_ev_guard(trade_id, ticker, live_spot, float(stop_loss or 0.0), direction, shares_cnt, option_pnl)

                # 2. STAGE 1: DYNAMIC ATR HARD STOP BREACHED
                ticker_data = self.levels_cache.get(ticker, {}) if isinstance(self.levels_cache.get(ticker), dict) else {}
                atr_14 = float(ticker_data.get("atr", live_spot * 0.035))
                atr_pct = atr_14 / live_spot
                max_loss_pct = max(0.20, min(0.42, atr_pct * 10.0))
                hard_stop_dollars = -1.0 * (estimated_basis * max_loss_pct)

                if option_pnl <= hard_stop_dollars:
                    print(f"[🚨 EMERGENCY ATR HARD STOP] {ticker}: Option loss ${option_pnl:.2f} reached ATR limit. Auto-Closing!")
                    conn_update = sqlite3.connect(DB_FILE)
                    conn_update.execute("""
                        UPDATE OR IGNORE trades 
                        SET exit_status = 'STOP_LOSS_ATR_HARD_CAP', exit_price = ?, net_pnl = ?, cso_notes = ? 
                        WHERE id = ?
                    """, (live_spot, trade_id, option_pnl, f"Reason: {cso_eval['reason']}", trade_id))
                    conn_update.commit()
                    conn_update.close()
                    continue

                # 3. STAGE 2: SOFT STOP (-20%) -> GEMINI CSO EVALUATION
                elif pnl_pct <= -0.20 and evaluate_macro_rebound is not None:
                    now_ts = time.time()
                    last_cso_call = self.cso_cooldowns.get(ticker, 0)

                    if now_ts - last_cso_call > 180:
                        self.cso_cooldowns[ticker] = now_ts
                        print(f"[🧠 CSO ESCALATION] {ticker} hit -20% soft stop. Requesting Gemini CSO Evaluation...")

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
                                UPDATE OR IGNORE trades 
                                SET exit_status = 'CSO_MACRO_CUT', exit_price = ?, net_pnl = ?, cso_notes = ? 
                                WHERE id = ?
                            """, (live_spot, trade_id, option_pnl, f"Reason: {cso_eval['reason']}", trade_id))
                            conn_update.commit()
                            conn_update.close()
                            continue

        except Exception as e:
            print(f"[!] MasterSentry Risk Audit Error: {e}")

def handle_shutdown_signal(signum=None, frame=None):
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
