import os
import sys
import json
import time
import sqlite3
import signal
import tempfile
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

def atomic_json_dump(data, filepath):
    dir_name = os.path.dirname(os.path.abspath(filepath)) or '.'
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tf:
        json.dump(data, tf, indent=2)
        temp_name = tf.name
    os.replace(temp_name, filepath)

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

def get_cso_status_reason(current_pnl_pct, peak_pnl_pct, tp_target_pct, last_heartbeat_ts, tradier_latency_sec, execution_error=None):
    now = time.time()
    heartbeat_age = round(now - last_heartbeat_ts, 1)

    # 🚨 CRITICAL SYSTEM WARNINGS (Catches Blocked / Asleep Engines)
    if heartbeat_age > 15.0:
        return f"🚨 CSO_BLOCKED [REASON: PROCESS_FROZEN | No Heartbeat in {heartbeat_age}s]"
    
    if tradier_latency_sec > 5.0:
        return f"⚠️ CSO_BLOCKED [REASON: MARKET_DATA_STALE | Latency: {tradier_latency_sec}s]"
        
    if execution_error:
        return f"🚨 CSO_ERROR [REASON: DISPATCH_FAILED | {execution_error}]"

    # ✅ HEALTHY STATE LOGIC (Normal Operating Modes)
    if peak_pnl_pct >= 0.30:
        trail_level = round((peak_pnl_pct - 0.015) * 100.0, 1)
        return f"CSO_HOLD [REASON: TIER_3_TRAIL_ACTIVE | Stop @ +{trail_level}% | Peak: +{round(peak_pnl_pct*100, 1)}%]"
    elif peak_pnl_pct >= 0.20:
        trail_level = round((peak_pnl_pct - 0.03) * 100.0, 1)
        return f"CSO_HOLD [REASON: TIER_2_TRAIL_ACTIVE | Stop @ +{trail_level}% | Peak: +{round(peak_pnl_pct*100, 1)}%]"
    elif peak_pnl_pct >= 0.10:
        trail_level = round((peak_pnl_pct - 0.05) * 100.0, 1)
        return f"CSO_HOLD [REASON: TIER_1_TRAIL_ACTIVE | Stop @ +{trail_level}% | Peak: +{round(peak_pnl_pct*100, 1)}%]"
    elif current_pnl_pct < tp_target_pct:
        gap = round((tp_target_pct - current_pnl_pct) * 100.0, 1)
        return f"CSO_HOLD [REASON: TARGET_PENDING | {gap}% to TP | Current: +{round(current_pnl_pct*100, 1)}%]"

    return "CSO_HOLD [REASON: EVALUATING_LEVELS]"

class MicroScalpSidekick:
    def __init__(self):
        self.active_windows = {} 
        self.levels_cache = {}
        self.last_levels_mtime = 0
        self.active_positions = {}
        self.cso_cooldowns = {} 
        self.cso_ev_state_cache = {} # State Transition Cache (ticker: {"state": str, "last_ping": float})
        self.peak_pnl_tracker = {}   # Persistent In-Memory Peak Return Tracker ({ticker: peak_pnl_pct})
        self.last_heartbeat = time.time()

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
        print("[✓] HARM.AI Sidekick Engine: Production-Grade Orchestrator Loaded with Multi-Tier CSO Context.")

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

    def process_cso_ev_guard(self, trade_id: int, ticker: str, live_spot: float, stop_loss_val: float, direction: str, shares_cnt: float, option_pnl: float, entry_price: float = 0.0):
        """State Transition Guard for CSO Expected Value (EV) exits."""
        gex_target, stop_loss_val, gex_label = resolve_direction_targets(ticker, live_spot, direction, stop_loss_val)
        
        if not gex_target:
            return

        if entry_price > 0 and (option_pnl == 0.0 or option_pnl is None):
            delta_val = float(delta) if ('delta' in locals() and delta and float(delta) > 0) else 0.50
            t_dict = trade if 'trade' in locals() else (pos if 'pos' in locals() else (position if 'position' in locals() else {}))
            entry_stock = float(t_dict.get('spot_price', 0) or t_dict.get('entry_spot', 0) or live_spot)
            stock_move = (live_spot - entry_stock) if str(direction).upper() == 'CALL' else (entry_stock - live_spot)
            effective_pnl = round(stock_move * delta_val * 100.0 * shares_cnt, 2) if entry_stock > 0 else 0.0
        else:
            effective_pnl = option_pnl

        hit_prob = calculate_gex_hit_probability(live_spot, gex_target, gex_label)
        eval_spot = entry_price if (entry_price > 0 and option_pnl == 0.0 and live_spot > entry_price * 2.0) else live_spot
        cso_eval = evaluate_cso_informed_exit(eval_spot, gex_target, stop_loss_val, hit_prob, effective_pnl, shares_cnt)
        recommendation = cso_eval["recommendation"]

        now_ts = time.time()
        cached = self.cso_ev_state_cache.get(ticker, {"state": "HOLD", "last_ping": 0})
        
        state_changed = (recommendation != cached["state"])
        time_elapsed = now_ts - cached["last_ping"]

        if state_changed or time_elapsed >= 120:
            print(f"[🧠 CSO EV ALERT] {ticker} -> Rec: {recommendation} | Effective PnL: ${effective_pnl:.2f} | Reason: {cso_eval['reason']}")
            self.cso_ev_state_cache[ticker] = {"state": recommendation, "last_ping": now_ts}

        # --- TIER 1: NON-NEGOTIABLE HARD RISK CAP (-$30.00) ---
        if effective_pnl <= -30.00:
            print(f"[🚨 CSO HARD RISK CAP] {ticker} breached -$30.00 risk cap (${effective_pnl:.2f}). Executing Non-Discretionary Close!")
            with sqlite3.connect(DB_FILE, timeout=30.0) as conn_cso:
                conn_cso.execute("""
                    UPDATE trades 
                    SET exit_status = 'CSO_RISK_CAP_STOP', exit_price = ?, net_pnl = ?, cso_notes = ?, exit_timestamp = datetime('now', 'localtime')
                    WHERE id = ? AND exit_status = 'ACTIVE'
                """, (live_spot, effective_pnl, f"Hard Cap Breached: ${effective_pnl:.2f}", trade_id))
                conn_cso.commit()
            return

        # --- TIER 2: CSO TACTICAL DECAY AUTO-EXIT ---
        if recommendation == "TIGHTEN_STOP" and effective_pnl <= -20.00:
            print(f"[🧠 CSO AUTO-EXIT] CSO EV Path degraded for {ticker} (${effective_pnl:.2f}). Executing Dynamic Exit!")
            with sqlite3.connect(DB_FILE, timeout=30.0) as conn_cso:
                conn_cso.execute("""
                    UPDATE trades 
                    SET exit_status = 'CSO_EV_DECAY_EXIT', exit_price = ?, net_pnl = ?, cso_notes = ?, exit_timestamp = datetime('now', 'localtime')
                    WHERE id = ? AND exit_status = 'ACTIVE'
                """, (live_spot, effective_pnl, f"CSO EV Alert: {cso_eval['reason']}", trade_id))
                conn_cso.commit()
            return

        # --- TIER 3: TAKE PROFIT AUTO-LOCK ---
        if recommendation == "TAKE_PROFIT_NOW":
            print(f"[🎯 CSO AUTO-LOCK GAINS] Closing {ticker} to secure ${effective_pnl:+.2f} profit!")
            with sqlite3.connect(DB_FILE, timeout=30.0) as conn_cso:
                conn_cso.execute("""
                    UPDATE trades 
                    SET exit_status = 'CSO_TAKE_PROFIT', exit_price = ?, net_pnl = ?, cso_notes = ?, exit_timestamp = datetime('now', 'localtime')
                    WHERE id = ? AND exit_status = 'ACTIVE'
                """, (live_spot, effective_pnl, f"CSO Target Hit: {cso_eval['reason']}", trade_id))
                conn_cso.commit()
            return

    def audit_active_positions(self):
        self.last_heartbeat = time.time()
        if not os.path.exists(DB_FILE):
            return
        try:
            conn = sqlite3.connect(DB_FILE, timeout=10.0)
            cursor = conn.cursor()
            
            try:
                cursor.execute("ALTER TABLE trades ADD COLUMN peak_pnl REAL DEFAULT 0.0")
                conn.commit()
            except sqlite3.OperationalError:
                pass
                
            cursor.execute("SELECT ticker, spot_price, stop_loss, take_profit, timestamp, entry_price, shares, direction, id, peak_pnl, occ_symbol FROM trades WHERE exit_status = 'ACTIVE'")
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
                peak_pnl_val = float(row[9]) if (len(row) > 9 and row[9] is not None) else 0.0
                occ_sym = row[10] if (len(row) > 10 and row[10]) else None

                t0 = time.time()
                stock_quote = get_live_quote(ticker)
                tradier_latency = round(time.time() - t0, 2)

                live_spot = float(stock_quote.get('last') or spot_price) if (stock_quote and stock_quote.get('last')) else spot_price
                ticker_data = self.levels_cache.get(ticker, {})

                opt_quote = get_live_quote(occ_sym) if occ_sym else None
                
                if opt_quote and opt_quote.get('last') and float(opt_quote['last']) > 0:
                    live_opt_price = float(opt_quote['last'])
                    option_pnl = round((live_opt_price - entry_price) * shares_cnt * 100.0, 2)
                else:
                    delta = 0.50
                    base_spot = spot_price if spot_price else live_spot
                    spot_diff = live_spot - base_spot if str(direction).upper() == 'CALL' else base_spot - live_spot
                    option_pnl = round(spot_diff * delta * 100.0 * shares_cnt, 2)
                    live_opt_price = entry_price + (option_pnl / (shares_cnt * 100.0)) if (shares_cnt > 0) else entry_price

                total_cost = max(30.0, entry_price * 100.0 * shares_cnt)
                current_pnl_pct = option_pnl / total_cost if total_cost > 0 else 0.0

                if option_pnl > peak_pnl_val:
                    with sqlite3.connect(DB_FILE, timeout=10.0) as conn_peak:
                        conn_peak.execute("UPDATE trades SET peak_pnl = ? WHERE id = ?", (option_pnl, trade_id))
                        conn_peak.commit()

                db_peak_dollars = max(peak_pnl_val, option_pnl)
                db_peak_pct = db_peak_dollars / total_cost if total_cost > 0 else 0.0

                self.peak_pnl_tracker[ticker] = max(self.peak_pnl_tracker.get(ticker, 0.0), db_peak_pct)
                peak_pnl_pct = self.peak_pnl_tracker[ticker]
                estimated_basis = max(30.0, entry_price * 100.0 * shares_cnt)
                pnl_pct = option_pnl / estimated_basis

                # --- CSO REASON EVALUATION & TELEMETRY UPDATE ---
                cso_reason = get_cso_status_reason(
                    current_pnl_pct=current_pnl_pct,
                    peak_pnl_pct=peak_pnl_pct,
                    tp_target_pct=0.50,
                    last_heartbeat_ts=self.last_heartbeat,
                    tradier_latency_sec=tradier_latency
                )

                with sqlite3.connect(DB_FILE, timeout=10.0) as conn_reason:
                    conn_reason.execute("UPDATE trades SET cso_notes = ? WHERE id = ? AND exit_status = 'ACTIVE'", (cso_reason, trade_id))
                    conn_reason.commit()

                # --- CSO DYNAMIC MULTI-TIER TRAILING PROFIT MATRIX ---
                trail_buffer = 0.0
                tier_label = ""

                if peak_pnl_pct >= 0.30:
                    trail_buffer = 0.015 # Maximum 1.5% tight trail at +30%+ gain
                    tier_label = "TIER 3 (+30% Peak / 1.5% Trail)"
                elif peak_pnl_pct >= 0.20:
                    trail_buffer = 0.03  # Tighter 3% trail at +20%+ gain
                    tier_label = "TIER 2 (+20% Peak / 3% Trail)"
                elif peak_pnl_pct >= 0.10:
                    trail_buffer = 0.05  # Standard 5% trail at +10%+ gain
                    tier_label = "TIER 1 (+10% Peak / 5% Trail)"

                if trail_buffer > 0.0:
                    floor_pct = peak_pnl_pct - trail_buffer
                    print(f"[🛡️ TRAILING LOCK {tier_label}] {ticker}: Peak = +{peak_pnl_pct*100:.1f}% | Current = +{current_pnl_pct*100:.1f}% | Floor = +{floor_pct*100:.1f}%")

                    if current_pnl_pct <= floor_pct:
                        print(f"[🚨 CSO TRAILING TRIGGERED] {ticker} peaked at +{peak_pnl_pct*100:.1f}%, dropped below floor (+{floor_pct*100:.1f}%). Executing Auto-Close!")
                        with sqlite3.connect(DB_FILE, timeout=10.0) as conn_trail:
                            conn_trail.execute("""
                                UPDATE trades 
                                SET exit_status = 'CSO_TRAILING_LOCK_EXIT', 
                                    exit_price = ?, 
                                    net_pnl = ?, 
                                    cso_notes = ?,
                                    exit_timestamp = datetime('now', 'localtime')
                                WHERE id = ? AND exit_status = 'ACTIVE'
                            """, (round(entry_price + (option_pnl / (shares_cnt * 100.0)), 2) if shares_cnt > 0 else live_spot, option_pnl, f"Trailing Lock Exit ({tier_label}): Peaked +{peak_pnl_pct*100:.1f}%, Dropped to +{current_pnl_pct*100:.1f}%", trade_id))
                            conn_trail.commit()
                        continue

                # 1. IMMEDIATE RATCHET: Lock gains if profit touched +$20 and retraced $10
                if db_peak_dollars >= 20.0 and (db_peak_dollars - option_pnl) >= 10.0:
                    with sqlite3.connect(DB_FILE, timeout=10.0) as conn_prot:
                        conn_prot.execute("""
                            UPDATE trades 
                            SET exit_status = 'CSO_MICRO_PROFIT_LOCK', 
                                exit_price = ?, 
                                net_pnl = ?, 
                                cso_notes = 'Capital Protector: Micro-profit trailing lock triggered',
                                exit_timestamp = datetime('now', 'localtime')
                            WHERE id = ? AND exit_status = 'ACTIVE'
                        """, (live_spot, option_pnl, trade_id))
                        conn_prot.commit()
                    print(f"[🛡️ CAPITAL PROTECTOR] Locked +${option_pnl:.2f} profit on {ticker}!")
                    continue

                # 2. Process CSO Expected Value Exit Guard
                self.process_cso_ev_guard(trade_id, ticker, live_spot, float(stop_loss or 0.0), direction, shares_cnt, option_pnl, entry_price)

                # 3. STAGE 1: STRICT $30.00 HARD RISK CAP & ATR BREACH
                MAX_RISK_CAP_DOLLARS = -30.00

                if option_pnl <= MAX_RISK_CAP_DOLLARS or (entry_price and (live_spot - entry_price) * shares_cnt * (-1 if direction == 'PUT' else 1) <= MAX_RISK_CAP_DOLLARS):
                    print(f"[🚨 HARD RISK CAP BREACHED] {ticker}: Option loss ${option_pnl:.2f} exceeded -$30.00 max risk limit! Triggering immediate market exit.")
                    with sqlite3.connect(DB_FILE, timeout=10.0) as conn_update:
                        conn_update.execute("""
                            UPDATE OR IGNORE trades 
                            SET exit_status = 'STOP_LOSS_ATR_HARD_CAP', exit_price = ?, net_pnl = ?, cso_notes = ?, exit_timestamp = datetime('now', 'localtime')
                            WHERE id = ?
                        """, (live_spot, option_pnl, "Reason: ATR Hard Cap Breached", trade_id))
                        conn_update.commit()
                    continue

                # 4. STAGE 2: SOFT STOP (-20%) -> GEMINI CSO EVALUATION
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
                            with sqlite3.connect(DB_FILE, timeout=10.0) as conn_update:
                                conn_update.execute("""
                                    UPDATE OR IGNORE trades 
                                    SET exit_status = 'CSO_MACRO_CUT', exit_price = ?, net_pnl = ?, cso_notes = ?, exit_timestamp = datetime('now', 'localtime')
                                    WHERE id = ?
                                """, (live_spot, option_pnl, f"Reason: {reasoning}", trade_id))
                                conn_update.commit()
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
    print("Target Session: Pure Tradier Stream & Multi-Tier Trailing Engine")
    print("=" * 65)

    sidekick = MicroScalpSidekick()
    
    try:
        while True:
            sidekick.load_tactical_levels()
            sidekick.audit_active_positions()
            time.sleep(10)
    except (KeyboardInterrupt, SystemExit):
        handle_shutdown_signal()
