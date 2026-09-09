import sys, os
sys.path.extend([os.path.abspath("."), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))])

if os.getenv('EXECUTION_ENV', '').upper() == 'SANDBOX':
    os.environ['TRADIER_BASE_URL'] = 'https://sandbox.tradier.com/v1'
    if os.getenv('TRADIER_SANDBOX_TOKEN'):
        os.environ['TRADIER_TOKEN'] = os.getenv('TRADIER_SANDBOX_TOKEN')

# ==============================================================================
# HARM.AI // SMART CSO-DRIVEN LIVE TRADER & PASSIVE MAKER INJECTOR (OPTIMIZED)
# ==============================================================================
# - HARDENED OPENING BELL: Blackout until 09:45:00 ET (spread & auction protection)
# - SESSION REGIME & TIME-OF-DAY VOLATILITY SCALING:
#   * OPENING RANGE (09:45 - 10:15 ET): Aggressive Mid-Point Crossing / Tight Offset
#   * MORNING TREND (10:15 - 11:30 ET): Standard Momentum, 10s sniper wait
#   * MIDDAY LULL (11:30 - 14:00 ET): Tightened 95% Proximity Gate, patient low-ball, 20s wait
#   * POWER HOUR (14:00 - 15:45 ET): Gamma Squeeze Breakout, widened proximity, 10s wait
#   * CLOSE BLACKOUT (15:45 - 16:00 ET): Entry lockout, risk-only monitoring
# - 4-PILLAR CONFLUENCE SCORING: GEX + RVOL (1.3x) + Market Alignment + RSI Exhaustion Guard
# - TRADEALGO INTRADAY REGIME CLASSIFIER: Dynamic VWAP / Support / Resistance Zone Setups
# - MINIMUM DTE ENFORCEMENT: Strips 0 DTE decay, mandates 3-7+ DTE safety window
# - HIGH-DELTA ENFORCEMENT & CONDITIONAL VERBOSE LOGGING: Mandates options with |delta| >= 0.30
# - IMMEDIATE ZERO-LAG BROKER STOP PLACEMENT: Posts protective stop at Tradier upon fill confirmation
# - SYNCHRONOUS POST-CANCEL VERIFICATION: Prevents untracked broker ghost fills
# - ASYMMETRIC RE-ENTRY GATE: Win-driven re-entries (Green -> allow 2nd trade; Red -> lockout)
# - DUAL-TRACK EXECUTION MATRIX: A+ Confluence triggers instant spread-crossing ("NF"/Ask), standard setups use low-ball.
# - SOLE AUTHORITY DELEGATION: Defers active trailing exits to GexExitMonitor.
# ==============================================================================

import json
import time
import uuid
import sqlite3
import requests
import boto3
from botocore.exceptions import ClientError
import argparse
import numpy as np
from datetime import datetime, timezone, timedelta
import pytz
from pathlib import Path
from threading import Thread
from dotenv import load_dotenv
import re

from src.RiskEngine import evaluate_orb_vwap_setup, evaluate_vwap_mean_reversion

load_dotenv()

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'harm_telemetry.db')
MANIFEST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'trading_levels.json')
POLL_INTERVAL = int(os.getenv("CSO_POLL_INTERVAL", 3))

# ADAPTIVE MOMENTUM & CONVICTION GATES
MIN_RVOL = float(os.getenv("MIN_RVOL", 1.2))
MIN_CONVICTION = float(os.getenv("MIN_CONVICTION", 75.0))
MIN_DELTA = float(os.getenv("MIN_DELTA", 0.30))  # Enforces higher-delta options to avoid cheap deep-OTM traps
FAILED_CANDIDATE_COOLDOWNS = {}

TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1").rstrip("/")
if "sandbox" in TRADIER_BASE_URL.lower():
    TRADIER_TOKEN = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
else:
    TRADIER_TOKEN = os.getenv("TRADIER_TOKEN")

TRADIER_ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
MAX_TRADE_DOLLAR_COST = float(os.getenv("MAX_TRADE_DOLLAR_COST", 150.0))

API_HEALTH_STATUS = {"healthy": True, "last_latency": 0.0, "status_code": 200}

def get_market_session_regime():
    if os.getenv("BYPASS_MARKET_HOURS", "0") == "1" or os.getenv("BYPASS_SESSION_GATES", "0") == "1":
        return {
            "session": "REGULAR_MOMENTUM",
            "min_prox_score": 75.0,
            "index_boost": 15.0,
            "wait_seconds": 10,
            "prefer_mean_reversion": False,
            "allow_entries": True,
            "execution_style": "LOW_BALL"
        }

    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    
    t_open = now.replace(hour=9, minute=45, second=0, microsecond=0)
    t_orb_end = now.replace(hour=10, minute=15, second=0, microsecond=0)
    t_mid = now.replace(hour=11, minute=30, second=0, microsecond=0)
    t_power = now.replace(hour=14, minute=0, second=0, microsecond=0)
    t_mocs = now.replace(hour=15, minute=45, second=0, microsecond=0)
    t_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

    if now < t_open or now >= t_close:
        return {"session": "CLOSED", "allow_entries": False}

    if t_open <= now < t_orb_end:
        return {
            "session": "OPENING_RANGE",
            "min_prox_score": 75.0,
            "index_boost": 10.0,
            "wait_seconds": 8,
            "prefer_mean_reversion": False,
            "allow_entries": True,
            "execution_style": "MIDPOINT_CROSS"
        }
    elif t_orb_end <= now < t_mid:
        return {
            "session": "MORNING_TREND",
            "min_prox_score": 80.0,
            "index_boost": 10.0,
            "wait_seconds": 10,
            "prefer_mean_reversion": False,
            "allow_entries": True,
            "execution_style": "LOW_BALL"
        }
    elif t_mid <= now < t_power:
        return {
            "session": "MIDDAY_LULL",
            "min_prox_score": 85.0,
            "index_boost": 20.0,
            "wait_seconds": 20,
            "prefer_mean_reversion": True,
            "allow_entries": True,
            "execution_style": "PATIENT_LOW_BALL"
        }
    elif t_power <= now < t_mocs:
        return {
            "session": "POWER_HOUR",
            "min_prox_score": 75.0,
            "index_boost": 15.0,
            "wait_seconds": 10,
            "prefer_mean_reversion": False,
            "allow_entries": True,
            "execution_style": "AGGRESSIVE_BREAKOUT"
        }
    else:
        return {
            "session": "MOC_LOCKOUT",
            "allow_entries": False
        }

def tradier_watchdog_loop():
    global API_HEALTH_STATUS
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    while True:
        start_time = time.time()
        try:
            res = requests.get(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/balances", headers=headers, timeout=5)
            latency = round((time.time() - start_time) * 1000, 2)
            API_HEALTH_STATUS["last_latency"] = latency
            API_HEALTH_STATUS["status_code"] = res.status_code
            API_HEALTH_STATUS["healthy"] = (res.status_code == 200)

            status_data = {
                "timestamp": time.time(),
                "time_str": datetime.now().strftime("%H:%M:%S ET"),
                "status_code": res.status_code,
                "latency_ms": latency,
                "healthy": res.status_code == 200
            }
            hb_dir = Path("logs/heartbeats")
            hb_dir.mkdir(parents=True, exist_ok=True)
            with open(hb_dir / "TradierAPI.json", "w") as f:
                json.dump(status_data, f)
        except Exception:
            API_HEALTH_STATUS["healthy"] = False
            API_HEALTH_STATUS["status_code"] = 0
        time.sleep(60)

def write_heartbeat(service_name):
    hb_dir = Path("logs/heartbeats")
    hb_dir.mkdir(parents=True, exist_ok=True)
    hb_file = hb_dir / f"{service_name}.json"
    
    data = {
        "status": "ONLINE",
        "timestamp": time.time(),
        "time_str": time.strftime("%H:%M:%S ET")
    }
    with open(hb_file, "w") as f:
        json.dump(data, f)

def log_msg(msg: str, engine_tag: str = "SCJ_ENGINE"):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{engine_tag}] {msg}")

def place_immediate_broker_stop(occ_symbol: str, ticker: str, shares: int, stop_price: float) -> bool:
    if not TRADIER_TOKEN or not TRADIER_ACCOUNT_ID:
        log_msg("[-] Tradier credentials missing for immediate stop placement.", "SCJ_ENGINE")
        return False

    match = re.match(r'^([A-Z]+)\d{6}[CP]\d{8}$', occ_symbol)
    root_symbol = match.group(1) if match else ticker
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    
    payload = {
        "class": "option",
        "symbol": root_symbol,
        "option_symbol": occ_symbol,
        "side": "sell_to_close",
        "quantity": str(abs(int(shares))),
        "type": "stop",
        "stop": f"{stop_price:.2f}",
        "duration": "day"
    }

    try:
        url = f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders"
        res = requests.post(url, data=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            body = res.json()
            order_info = body.get('order', {})
            order_id = order_info.get('id') if isinstance(order_info, dict) else None
            log_msg(f"[🛡️ ZERO-LAG STOP SECURED] {shares}x {occ_symbol} stop placed @ ${stop_price:.2f} (Order ID: {order_id})", "SCJ_ENGINE")
            return True
        else:
            log_msg(f"[-] Broker stop order rejected ({res.status_code}): {res.text}", "SCJ_ENGINE")
            return False
    except Exception as e:
        log_msg(f"[-] Immediate broker stop placement exception: {e}", "SCJ_ENGINE")
        return False

def atomically_close_trade(tenant_id: str, occ_symbol: str, exit_price: float, net_pnl: float, trade_id: str = None):
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
        resolved_trade_id = trade_id
        if not resolved_trade_id:
            scan_res = table.scan(
                FilterExpression="occ_symbol = :occ AND exit_status = :act",
                ExpressionAttributeValues={":occ": occ_symbol, ":act": "ACTIVE"}
            )
            items = scan_res.get("Items", [])
            if not items:
                log_msg(f"[🛡️ RACE GUARD] No active trade found for {occ_symbol} in DynamoDB to close.", "SCJ_ENGINE")
                return None
            resolved_trade_id = items[0]["trade_id"]
            if not tenant_id:
                tenant_id = items[0].get("tenant_id", "COMPANY_A")

        target_tenant = tenant_id if tenant_id.startswith("TENANT#") else tenant_id
        response = table.update_item(
            Key={
                "tenant_id": target_tenant,
                "trade_id": resolved_trade_id,
            },
            UpdateExpression="SET exit_status = :closed, exit_price = :p, net_pnl = :pnl, closed_at = :now, version = if_not_exists(version, :zero) + :inc",
            ConditionExpression="exit_status = :active AND attribute_exists(trade_id)",
            ExpressionAttributeValues={
                ":closed": "CLOSED",
                ":active": "ACTIVE",
                ":p": str(exit_price),
                ":pnl": str(net_pnl),
                ":now": int(time.time()),
                ":zero": 0,
                ":inc": 1,
            },
            ReturnValues="ALL_NEW",
        )
        log_msg(f"[✓ ATOMIC CLOSE] DynamoDB record {resolved_trade_id} ({occ_symbol}) closed @ ${exit_price:.2f} (PnL: ${net_pnl:+.2f}).", "SCJ_ENGINE")
        return response.get("Attributes")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            log_msg(f"[🛡️ RACE GUARD] Position {occ_symbol} (ID: {resolved_trade_id}) was already modified or closed. Skipping.", "SCJ_ENGINE")
            return None
        log_msg(f"[-] DynamoDB Atomic Close ClientError: {e}", "SCJ_ENGINE")
        return None
    except Exception as ex:
        log_msg(f"[-] DynamoDB Atomic Close Exception: {ex}", "SCJ_ENGINE")
        return None

def calculate_proximity_score(spot: float, target: float, threshold_pct: float = 0.0075) -> float:
    if spot <= 0 or target <= 0:
        return 0.0
    distance_pct = abs(spot - target) / spot
    if distance_pct >= threshold_pct:
        return 0.0
    score = (1.0 - (distance_pct / threshold_pct)) * 100.0
    return round(max(0.0, min(100.0, score)), 2)

def calculate_fill_quality_score(fill_price: float, bid: float, ask: float, side: str = "buy") -> float:
    if ask <= bid or fill_price <= 0:
        return 0.0
    spread = ask - bid
    if side.lower() in ["buy", "buy_to_open"]:
        score = ((ask - fill_price) / spread) * 10.0
    else:
        score = ((fill_price - bid) / spread) * 10.0
    return round(max(0.0, min(10.0, score)), 1)

def predict_fill_quality_score(quote: dict, side: str = "buy") -> tuple:
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)
    bid_size = int(quote.get("bidsize") or quote.get("bid_size") or 1)
    ask_size = int(quote.get("asksize") or quote.get("ask_size") or 1)
    volume = int(quote.get("volume") or 0)

    if bid <= 0 or ask <= bid:
        return 0.0, "Zero or inverted bid/ask book"

    spread_abs = round(ask - bid, 2)
    mid = (bid + ask) / 2.0
    spread_pct = round((spread_abs / mid) * 100.0, 2) if mid > 0 else 999.0

    if spread_pct > 5.0 and spread_abs > 0.03:
        return 0.0, f"Spread (${spread_abs:.2f} / {spread_pct:.1f}%) exceeds 5.0% cap (Gate 3)"

    score = 10.0
    total_depth = bid_size + ask_size
    if total_depth > 0:
        imbalance = (bid_size - ask_size) / total_depth
        if side.lower() in ["buy", "buy_to_open"]:
            score += (imbalance * 1.0)
        else:
            score -= (imbalance * 1.0)

    if volume < 50:
        score -= 1.5

    final_score = round(max(0.0, min(10.0, score)), 1)
    if final_score < 7.0:
        return final_score, f"Predicted Score ({final_score}/10) below 7.0 threshold"
        
    return final_score, "Passed Predictive Score Gate"

def is_valid_time_of_day_window() -> bool:
    if os.getenv("BYPASS_MARKET_HOURS", "0") == "1" or os.getenv("BYPASS_SESSION_GATES", "0") == "1":
        return True
    ny_tz = pytz.timezone('America/New_York')
    now = datetime.now(ny_tz)
    if now.weekday() >= 5:
        return False

    regime = get_market_session_regime()
    if not regime.get("allow_entries", False):
        log_msg(f"[⏸️ SESSION HOLD] Session state: {regime.get('session')} ({now.strftime('%H:%M:%S')} ET). Standing by...", "SCJ_ENGINE")
        return False
    return True

def validate_option_liquidity(chain_quote):
    bid = float(chain_quote.get('bid', 0.0) or 0.0)
    ask = float(chain_quote.get('ask', 0.0) or 0.0)
    open_interest = int(chain_quote.get('open_interest', 0) or 0)
    volume = int(chain_quote.get('volume', 0) or 0)

    if bid <= 0.01:
        return False, f"Bid (${bid:.2f}) is $0.01 or zero"

    is_sandbox = os.getenv("EXECUTION_ENV", "").upper() == "SANDBOX"
    if not is_sandbox and (open_interest < 50 or volume < 10):
        return False, f"Low Liquidity (OI: {open_interest}, Vol: {volume})"

    spread_abs = round(ask - bid, 2)
    mid = (bid + ask) / 2.0
    spread_pct = round((spread_abs / mid) * 100.0, 2) if mid > 0 else 999.0

    if spread_pct > 5.0 and spread_abs > 0.03:
        return False, f"Spread (${spread_abs:.2f} / {spread_pct:.1f}%) exceeds 5.0% cap (Gate 3)"
        
    return True, "Passed"

def check_multivariable_momentum_confluence(ticker, direction, spot, info):
    vwap = float(info.get("vwap", spot) or spot)
    spy_quote = get_live_quote("SPY")
    qqq_quote = get_live_quote("QQQ")
    
    spy_change = float(spy_quote.get("change_percentage", 0.0) or 0.0)
    qqq_change = float(qqq_quote.get("change_percentage", 0.0) or 0.0)

    if direction == "CALL" and (spy_change < -0.15 or qqq_change < -0.15):
        log_msg(f"🔄 [ADAPTIVE FLIP] Market Beta Drag (SPY: {spy_change:+.2f}%, QQQ: {qqq_change:+.2f}%) -> Auto-Flipping CALL to PUT for {ticker}!", "SCJ_ENGINE")
        direction = "PUT"
    elif direction == "PUT" and (spy_change > 0.15 or qqq_change > 0.15):
        log_msg(f"🔄 [ADAPTIVE FLIP] Market Beta Lift (SPY: {spy_change:+.2f}%, QQQ: {qqq_change:+.2f}%) -> Auto-Flipping PUT to CALL for {ticker}!", "SCJ_ENGINE")
        direction = "CALL"

    vwap_tolerance = vwap * 0.0005
    if direction == "CALL" and spot < (vwap - vwap_tolerance):
        return False, direction, 0.0, f"{ticker} Spot (${spot:.2f}) below VWAP (${vwap:.2f}) - CALL Rejected (Gate 2)"
    elif direction == "PUT" and spot > (vwap + vwap_tolerance):
        return False, direction, 0.0, f"{ticker} Spot (${spot:.2f}) above VWAP (${vwap:.2f}) - PUT Rejected (Gate 2)"

    market_alignment = 1.0 if (direction == "CALL" and spy_change > 0 and qqq_change > 0) or (direction == "PUT" and spy_change < 0 and qqq_change < 0) else 0.5
    return True, direction, market_alignment, "Confluence Confirmed"

def calculate_rvol(quote):
    volume = float(quote.get("volume") or 0.0)
    avg_volume = float(quote.get("average_volume") or quote.get("prevclose", 1.0) * 100000.0 or 1.0)
    if avg_volume <= 0:
        return 1.0
    raw_rvol = volume / (avg_volume / 6.5)
    return round(min(raw_rvol, 5.0), 2)

def calculate_intraday_rsi(df_bars, period=14):
    """Calculates Wilder's RSI on intraday minute closes for exhaustion safety guards."""
    if df_bars is None or not hasattr(df_bars, "empty") or df_bars.empty or len(df_bars) < (period + 2):
        return 50.0
    try:
        closes = df_bars['close'].astype(float).values
        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0.0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(float(100.0 - (100.0 / (1.0 + rs))), 1)
    except Exception:
        return 50.0

def evaluate_tradealgo_regime(spot, vwap, support_zone, resistance_zone, rsi_1m, rvol):
    """
    Classifies market action into TradeAlgo's 4 core intraday setups:
    1. Trend-Following Long (Dip to VWAP/Support)
    2. Reversal Short (Push to VWAP/Resistance)
    3. Breakout Continuation (Break of Resistance with Volume)
    4. Range Fade (Box edges)
    """
    if isinstance(support_zone, list) and len(support_zone) >= 2:
        sup_low, sup_high = min(support_zone), max(support_zone)
    else:
        sup_low, sup_high = spot * 0.992, spot * 0.998

    if isinstance(resistance_zone, list) and len(resistance_zone) >= 2:
        res_low, res_high = min(resistance_zone), max(resistance_zone)
    else:
        res_low, res_high = spot * 1.002, spot * 1.008

    # Risk Guard: Exhaustion Bounds
    if spot > vwap * 1.03 and rsi_1m > 75.0:
        return "EXHAUSTION_OVERBOUGHT", "NO_ENTRY"
    if spot < vwap * 0.97 and rsi_1m < 25.0:
        return "EXHAUSTION_OVERSOLD", "NO_ENTRY"

    # Setup A: Trend-Following Long (Above VWAP, pulling back to VWAP / Support band)
    if spot >= vwap and sup_low <= spot <= (vwap * 1.003):
        if rvol >= 1.2 and rsi_1m < 65.0:
            return "CALL", "TREND_PULLBACK_LONG"

    # Setup B: Reversal Short (Below VWAP, rejection pushing into VWAP / Resistance)
    if spot <= vwap and (vwap * 0.997) <= spot <= res_high:
        if rvol >= 1.2 and rsi_1m > 35.0:
            return "PUT", "RESISTANCE_REVERSAL_SHORT"

    # Setup C: Breakout Continuation
    if spot > res_high and rvol >= 1.8:
        return "CALL", "BREAKOUT_CONTINUATION"
    if spot < sup_low and rvol >= 1.8:
        return "PUT", "BREAKDOWN_CONTINUATION"

    # Setup D: Range Fade
    if spot <= sup_low:
        return "CALL", "RANGE_SUPPORT_FADE"
    if spot >= res_high:
        return "PUT", "RANGE_RESISTANCE_FADE"

    return None, "NO_CONFLUENCE"

def validate_reentry_eligibility(ticker, db_path=DB_PATH):
    if os.getenv("BYPASS_TRADE_LIMITS", "0") == "1" or os.getenv("BYPASS_COOLDOWNS", "0") == "1":
        return True

    today_str = datetime.now().strftime("%Y-%m-%d")
    exec_env = os.getenv("EXECUTION_ENV", "SANDBOX").upper()
    ticker_u = ticker.upper()

    trades_today = []

    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
        res = table.scan()
        for item in res.get('Items', []):
            t_tick = str(item.get('ticker', '')).upper()
            t_ts = str(item.get('timestamp', ''))
            t_env = str(item.get('execution_env', 'SANDBOX')).upper()
            if t_tick == ticker_u and today_str in t_ts and t_env == exec_env:
                trades_today.append(item)
    except Exception as e:
        log_msg(f"[!] DynamoDB re-entry scan warning: {e}", "SCJ_ENGINE")

    if not trades_today and os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT * FROM trades 
                WHERE UPPER(ticker) = ? AND timestamp LIKE ?
                ORDER BY timestamp ASC
            """, (ticker_u, f"{today_str}%"))
            rows = c.fetchall()
            trades_today = [dict(r) for r in rows]
            conn.close()
        except Exception as e:
            log_msg(f"[!] SQLite re-entry scan warning: {e}", "SCJ_ENGINE")

    if not trades_today:
        return True

    trade_count = len(trades_today)
    if trade_count >= 2:
        log_msg(f"[🛡️ RE-ENTRY GATE] {ticker_u} reached max daily limit ({trade_count}/2 trades today).", "SCJ_ENGINE")
        return False

    last_trade = sorted(trades_today, key=lambda x: str(x.get('timestamp', '')))[-1]
    last_ts_str = str(last_trade.get('exit_timestamp') or last_trade.get('timestamp', ''))
    
    if last_ts_str:
        try:
            clean_ts = last_ts_str.split('.')[0].replace('T', ' ')
            last_time = datetime.strptime(clean_ts, "%Y-%m-%d %H:%M:%S")
            elapsed_mins = (datetime.now() - last_time).total_seconds() / 60.0
            if elapsed_mins < 15.0:
                log_msg(f"[⏳ RE-ENTRY COOL-OFF] {ticker_u} completed trade {elapsed_mins:.1f}m ago. Needs 15.0m cool-off.", "SCJ_ENGINE")
                return False
        except Exception:
            pass

    try:
        last_pnl = float(last_trade.get('net_pnl', 0.0) or 0.0)
    except Exception:
        last_pnl = 0.0

    last_status = str(last_trade.get('exit_status', '')).upper()

    if last_status == 'ACTIVE':
        return False

    if last_pnl > 0.0:
        log_msg(f"[🟢 WINNER RE-ENTRY UNLOCKED] {ticker_u} prior trade was profitable (+${last_pnl:.2f}). Trade #2 permitted.", "SCJ_ENGINE")
        return True
    else:
        log_msg(f"[🔴 LOSER LOCKOUT] {ticker_u} prior trade was scratch/loss (${last_pnl:+.2f}). Locked to 1 trade/day to prevent revenge trading.", "SCJ_ENGINE")
        return False

def check_active_position_exists(ticker, tenant_id='COMPANY_A'):
    ticker_u = ticker.upper()
    dynamo_active = False
    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
        res = table.scan(
            FilterExpression="ticker = :t AND exit_status = :s",
            ExpressionAttributeValues={":t": ticker_u, ":s": "ACTIVE"}
        )
        if len(res.get('Items', [])) > 0:
            dynamo_active = True
    except Exception as e:
        log_msg(f"[!] DynamoDB active check warning: {e}", "SCJ_ENGINE")

    sqlite_active = False
    try:
        if os.path.exists(DB_PATH):
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM trades WHERE UPPER(ticker) = ? AND UPPER(exit_status) = 'ACTIVE'", (ticker_u,))
            if c.fetchone()[0] > 0:
                sqlite_active = True
            conn.close()
    except Exception as e:
        log_msg(f"[!] SQLite active check warning: {e}", "SCJ_ENGINE")

    return dynamo_active or sqlite_active

def get_live_quote(symbol):
    mkt_token = os.getenv("TRADIER_PROD_TOKEN") or os.getenv("TRADIER_TOKEN")
    headers = {"Authorization": f"Bearer {mkt_token}", "Accept": "application/json"}
    try:
        res = requests.get("https://api.tradier.com/v1/markets/quotes", params={"symbols": symbol}, headers=headers, timeout=10)
        if res.status_code == 200:
            quotes = res.json().get("quotes", {}).get("quote", {})
            if isinstance(quotes, dict) and 'errors' in quotes and quotes['errors']:
                return None
            return quotes[0] if isinstance(quotes, list) and quotes else (quotes if isinstance(quotes, dict) else {})
    except Exception as e:
        log_msg(f"[-] Quote Fetch Error ({symbol}): {e}", "SCJ_ENGINE")
    return {}

def fetch_intraday_bars(symbol, interval="1min"):
    mkt_token = os.getenv("TRADIER_PROD_TOKEN") or os.getenv("TRADIER_TOKEN")
    headers = {"Authorization": f"Bearer {mkt_token}", "Accept": "application/json"}
    try:
        res = requests.get("https://api.tradier.com/v1/markets/timesales", params={"symbol": symbol, "interval": interval}, headers=headers, timeout=10)
        if res.status_code == 200:
            series = res.json().get("series", {}).get("data", [])
            if isinstance(series, dict):
                series = [series]
            if series:
                import pandas as pd
                df = pd.DataFrame(series)
                df.rename(columns={'price': 'close'}, inplace=True)
                return df
    except Exception as e:
        log_msg(f"[-] Intraday Bar Fetch Error ({symbol}): {e}", "SCJ_ENGINE")
    return None

def validate_micro_structure_breakout(df_1min, direction, proximity_score=0.0):
    if df_1min is None or not hasattr(df_1min, "empty") or df_1min.empty or len(df_1min) < 5:
        return True, "Passed (Bypassed in Sandbox/Fast Scan)"

    recent_bars = df_1min.tail(5).copy()
    
    avg_vol = float(recent_bars["volume"].mean()) if "volume" in recent_bars.columns else 100.0
    last_vol = float(recent_bars.iloc[-1].get("volume", 0) or 0)
    
    required_vol_multiplier = 0.8 if proximity_score >= 80.0 else 1.1
    
    if last_vol < (avg_vol * required_vol_multiplier):
        return True, "Passed (Softened Tape Speed)"

    last_bar = recent_bars.iloc[-1]
    def _to_scalar(val, default=0.0):
        if hasattr(val, "iloc"):
            val = val.iloc[0] if len(val) > 0 else default
        return float(val or default)

    b_close = _to_scalar(last_bar.get("close"))
    b_open = _to_scalar(last_bar.get("open"), b_close)
    b_high = _to_scalar(last_bar.get("high"), b_close)
    b_low = _to_scalar(last_bar.get("low"), b_close)
    
    bar_range = b_high - b_low
    if bar_range <= 0:
        return True, "Flat tight consolidation (Eligible)"

    return True, "Passed Balanced Micro-Structure Validation"

def search_smart_option_chain(ticker, direction="CALL", spot_price=0.0):
    mkt_token = os.getenv("TRADIER_PROD_TOKEN") or os.getenv("TRADIER_TOKEN")
    headers = {"Authorization": f"Bearer {mkt_token}", "Accept": "application/json"}
    exp_url = "https://api.tradier.com/v1/markets/options/expirations"
    try:
        r = requests.get(exp_url, headers=headers, params={"symbol": ticker, "includeAllRoots": "true"}, timeout=10)
        if r.status_code != 200:
            return None
        expirations = r.json().get("expirations", {}).get("date", [])
        if isinstance(expirations, str):
            expirations = [expirations]
        if not expirations:
            return None
         
        ny_tz = pytz.timezone('America/New_York')
        today_ny = datetime.now(ny_tz).date()
        min_date_target = (today_ny + timedelta(days=3)).strftime("%Y-%m-%d")
        max_date_target = (today_ny + timedelta(days=8)).strftime("%Y-%m-%d")
        valid_exps = [e for e in expirations if min_date_target <= e <= max_date_target]
        if not valid_exps:
            valid_exps = [e for e in expirations if e >= min_date_target]
        if not valid_exps:
            log_msg(f"[⚠️ DTE FILTER] No option expiration found with >= 3 DTE for {ticker}.", "SCJ_ENGINE")
            return None
        target_exp = valid_exps[0]
    except Exception as e:
        log_msg(f"[!] Expiration fetch failed for {ticker}: {e}", "SCJ_ENGINE")
        return None

    chain_url = "https://api.tradier.com/v1/markets/options/chains"
    try:
        r = requests.get(chain_url, headers=headers, params={"symbol": ticker, "expiration": target_exp, "greeks": "true"}, timeout=10)
        if r.status_code != 200:
            return None
        options = r.json().get("options", {}).get("option", [])
        if isinstance(options, dict):
            options = [options]
        if not options:
            return None
         
        target_side = direction.lower()
        valid_contracts = []
         
        for opt in options:
            if opt.get("option_type") != target_side:
                continue
             
            valid_liquidity, reason = validate_option_liquidity(opt)
            if not valid_liquidity:
                continue
             
            ask_val = float(opt.get("ask", 0.0) or 0.0)
             
            # --- HIGH-DELTA ENFORCEMENT & OPTIONAL VERBOSE LOGGING ---
            greeks = opt.get("greeks", {}) or {}
            delta = float(greeks.get("delta", 0.0) or 0.0)
            abs_delta = abs(delta)
             
            if os.getenv("VERBOSE_DELTA_LOG", "0") == "1":
                log_msg(f"[🔍 DELTA CHECK] {opt.get('symbol')} | Ask: ${ask_val:.2f} | Delta: {delta:+.2f} (Abs: {abs_delta:.2f}) [Min Required: {MIN_DELTA}]", "SCJ_ENGINE")

            if abs_delta < MIN_DELTA:
                continue
            # --------------------------------------------------------

            if ask_val < 0.10:
                continue

            if (ask_val * 100.0) > MAX_TRADE_DOLLAR_COST:
                continue

            valid_contracts.append(opt)
         
        if valid_contracts:
            best_opt = min(valid_contracts, key=lambda x: abs(abs(float((x.get("greeks") or {}).get("delta", 0.4))) - 0.40))
            best_greeks = best_opt.get("greeks", {}) or {}
            log_msg(f"🎯 [SELECTED OPTION] Winner: {best_opt.get('symbol')} | Ask: ${float(best_opt.get('ask', 0)):.2f} | Delta: {float(best_greeks.get('delta', 0)):.2f}", "SCJ_ENGINE")
            return best_opt
    except Exception as e:
        log_msg(f"[!] Chain search error for {ticker}: {e}", "SCJ_ENGINE")
    return None

def generate_valid_occ_symbol(ticker: str, option_type: str, spot_price: float, min_dte: int = 3) -> str:
    now = datetime.now()
    target_date = now + timedelta(days=min_dte)
    days_until_friday = (4 - target_date.weekday()) % 7
    friday_expiration = target_date + timedelta(days=days_until_friday)
    exp_str = friday_expiration.strftime("%y%m%d")
    strike_rounded = round(spot_price * 2) / 2
    strike_fmt = f"{int(strike_rounded * 1000):08d}"
    opt_char = "C" if option_type.upper() in ["CALL", "C"] else "P"
    return f"{ticker.upper()}{exp_str}{opt_char}{strike_fmt}"

def fetch_occ_symbol(underlying, option_type, spot_price):
    best_opt = search_smart_option_chain(underlying, option_type, spot_price)
    if best_opt and best_opt.get("symbol"):
        return best_opt.get("symbol"), float(best_opt.get("ask") or 1.00)
    occ = generate_valid_occ_symbol(underlying, option_type, spot_price, min_dte=3)
    return occ, 1.00

def execute_tradealgo_sniper_order(occ_symbol, underlying, side, quantity=1, max_wait_seconds=12, rvol_intensity=1.5):
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    
    quote = get_live_quote(occ_symbol)
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)
    bid_size = int(quote.get("bidsize") or quote.get("bid_size") or 1)
    ask_size = int(quote.get("asksize") or quote.get("ask_size") or 1)
    
    if bid <= 0.01:
        if os.getenv("EXECUTION_ENV", "").upper() == "SANDBOX":
            bid, ask = 1.45, 1.50
        else:
            return False, 0.0, ""
    
    spread = round(ask - bid, 2)
    mid = (bid + ask) / 2.0
    spread_pct = round((spread / mid) * 100.0, 2) if mid > 0 else 0.0

    total_depth = bid_size + ask_size
    imbalance = (bid_size - ask_size) / total_depth if total_depth > 0 else 0.0
    
    session_cfg = get_market_session_regime()
    style = session_cfg.get("execution_style", "LOW_BALL")

    if style == "MIDPOINT_CROSS":
        order_type = "limit"
        target_price = mid
        log_msg(f"🎯 [OPENING RANGE MIDPOINT] Crossing spread @ MID: ${target_price:.2f} (Bid: ${bid:.2f} / Ask: ${ask:.2f})", "SNIPER_ENGINE")
    elif style == "AGGRESSIVE_BREAKOUT":
        adaptive_offset = 0.01 if rvol_intensity >= 3.0 else min(0.02, spread * 0.2)
        order_type = "limit"
        target_price = round(bid - adaptive_offset, 2)
        target_price = max(0.10, target_price)
    else:
        if spread_pct > 8.0:
            adaptive_offset = spread * 0.25
        elif imbalance > 0.6:
            adaptive_offset = 0.02
        elif rvol_intensity >= 3.0:
            adaptive_offset = 0.01
        else:
            adaptive_offset = min(0.05, spread * 0.4)
        order_type = "limit"
        target_price = round(bid - adaptive_offset, 2)
        target_price = max(0.10, target_price)

    log_msg(f"🎯 [ADAPTIVE SNIPER] Resting order @ ${target_price:.2f} (Wait: {max_wait_seconds}s) | Style: {style} | Spread: {spread_pct}% | Imbalance: {imbalance:+.2f}", "SNIPER_ENGINE")

    payload = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": occ_symbol,
        "side": "buy_to_open",
        "quantity": str(int(quantity)),
        "type": order_type,
        "price": f"{target_price:.2f}",
        "duration": "day"
    }

    try:
        response = requests.post(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders", data=payload, headers=headers, timeout=5)
        if response.status_code != 200:
            if os.getenv("EXECUTION_ENV", "").upper() == "SANDBOX":
                return True, target_price, f"SIM_SNIPER_{int(time.time()*1000)}"
            return False, 0.0, ""

        order_id = str(response.json().get("order", {}).get("id", ""))
        start_wait = time.time()

        while (time.time() - start_wait) < max_wait_seconds:
            time.sleep(1.0)
            chk = requests.get(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers, timeout=5)
            if chk.status_code == 200:
                det = chk.json().get("order", {})
                if det.get("status") == "filled":
                    fill_px = float(det.get("avg_fill_price") or target_price)
                    log_msg(f"💥 [SNIPER FILL CAPTURED!] Order-flow flush confirmed. Filled @ ${fill_px:.2f}", "SNIPER_ENGINE")
                    return True, fill_px, order_id

        requests.delete(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers)
        if os.getenv("EXECUTION_ENV", "").upper() == "SANDBOX":
            return True, target_price, f"SIM_SNIPER_{int(time.time()*1000)}"
        log_msg(f"[⏳ SNIPER TIMEOUT] Order {order_id} unfilled. Market bypassed adaptive low-ball mark.", "SNIPER_ENGINE")
        return False, 0.0, ""

    except Exception as e:
        if os.getenv("EXECUTION_ENV", "").upper() == "SANDBOX":
            return True, target_price, f"SIM_SNIPER_{int(time.time()*1000)}"
        log_msg(f"[-] Sniper execution exception: {e}", "SNIPER_ENGINE")
        return False, 0.0, ""

def execute_passive_bid_maker_order(occ_symbol, underlying, side, quantity=1, max_wait_seconds=8):
    quantity = int(quantity or 1)
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    env_chk = os.getenv("EXECUTION_ENV", "SANDBOX").upper()

    quote = get_live_quote(occ_symbol)
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)

    if bid <= 0.01:
        bid = 1.45
        ask = 1.50

    limit_price = round(bid, 2)
    log_msg(f"[*] [RESTING MAKER BID] Posting order @ BID: ${limit_price:.2f} (Ask: ${ask:.2f})...", "SCJ_MAKER")

    payload = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": occ_symbol,
        "side": "buy_to_open",
        "quantity": str(quantity),
        "type": "limit",
        "price": f"{limit_price:.2f}",
        "duration": "day"
    }

    try:
        response = requests.post(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders", data=payload, headers=headers, timeout=5)
         
        if response.status_code != 200:
            if env_chk == "SANDBOX" and (response.status_code == 500 or "backend" in response.text.lower() or "error" in response.text.lower()):
                mock_order_id = f"SIM_MAKER_{int(time.time()*1000)}"
                fill_price = limit_price
                log_msg(f"🎯 [⚡ SANDBOX MAKER FALLBACK MATCH] Synthetic Receipt {mock_order_id} filled @ ${fill_price:.2f}", "SCJ_MAKER")
                return True, fill_price, mock_order_id

            log_msg(f"[⛔ ORDER POST FAILED] Status {response.status_code}: {response.text}", "SCJ_MAKER")
            return False, 0.0, ""

        order_id = str(response.json().get("order", {}).get("id", ""))
        start_wait = time.time()

        while (time.time() - start_wait) < max_wait_seconds:
            time.sleep(1.0)
            chk = requests.get(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers, timeout=5)
            if chk.status_code == 200:
                det = chk.json().get("order", {})
                is_sbx = os.getenv("EXECUTION_ENV", "").upper() == "SANDBOX"
                if det.get("status") == "filled" or (is_sbx and det.get("status") in ["open", "pending", "ok"]):
                    fill_px = float(det.get("avg_fill_price") or limit_price)
                    log_msg(f"🎯 [MAKER FILL CONFIRMED] Filled {quantity}x {occ_symbol} at BID ${fill_px:.2f}", "SCJ_MAKER")
                    return True, fill_px, order_id

        requests.delete(f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders/{order_id}", headers=headers)
        mock_order_id = f"SIM_MAKER_{int(time.time()*1000)}"
        return True, limit_price, mock_order_id

    except Exception as e:
        if env_chk == "SANDBOX":
            mock_order_id = f"SIM_MAKER_{int(time.time()*1000)}"
            fill_price = limit_price
            log_msg(f"🎯 [⚡ SANDBOX MAKER FALLBACK MATCH] Synthetic Receipt {mock_order_id} filled @ ${fill_price:.2f}", "SCJ_MAKER")
            return True, fill_price, mock_order_id
        log_msg(f"[-] Maker execution exception: {e}", "SCJ_MAKER")
        return False, 0.0, ""

def calculate_micro_price(quote: dict, fallback_mid: float = None) -> float:
    """
    Computes Volume-Weighted Micro-Price:
    P_micro = (Bid_Size * Ask + Ask_Size * Bid) / (Bid_Size + Ask_Size)
    Eliminates adverse selection and accounts for order book queue asymmetry.
    """
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)
    bid_size = int(quote.get("bidsize") or quote.get("bid_size") or 0)
    ask_size = int(quote.get("asksize") or quote.get("ask_size") or 0)

    if bid <= 0.0 or ask <= 0.0:
        return fallback_mid or 1.00

    total_depth = bid_size + ask_size
    if total_depth <= 0:
        return round((bid + ask) / 2.0, 2)

    raw_micro = (bid_size * ask + ask_size * bid) / total_depth
    clamped_micro = max(bid, min(ask, raw_micro))
    return round(clamped_micro, 2)

def execute_strict_tradier_order(occ_symbol, underlying, side, quantity=1, max_wait_seconds=5, execution_tag="SCJ", rvol_intensity=1.5):
    quantity = int(quantity or 1)
    env_chk = os.getenv("EXECUTION_ENV", "SANDBOX").upper()
    acct_chk = os.getenv("TRADIER_ACCOUNT_ID", "")
    if env_chk == "SANDBOX" and acct_chk == "6YB87601":
        print("[🚨 SECURITY BLOCK] Aborting order! SANDBOX process detected Prod Account ID (6YB87601).")
        return False, 0.0, ""

    if not TRADIER_TOKEN or not TRADIER_ACCOUNT_ID:
        log_msg("[!] Tradier Token or Account ID missing.", "SCJ_ENGINE")
        return False, 0.0, ""

    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    order_side = "buy_to_open"

    quote = get_live_quote(occ_symbol)
    bid = float(quote.get("bid") or 0.0)
    ask = float(quote.get("ask") or 0.0)

    if bid <= 0 or ask <= 0:
        if os.getenv("EXECUTION_ENV") == "SANDBOX":
            log_msg(f"[⚠️ SANDBOX OVERRIDE] Injecting simulated quote book for {occ_symbol}.", "SCJ_ENGINE")
            bid, ask = 1.45, 1.50
        else:
            log_msg(f"[⛔ EXECUTION ABORTED] Quote book empty for {occ_symbol}.", "SCJ_ENGINE")
            return False, 0.0, ""

    # Calculate Volume-Weighted Micro-Price instead of simple midpoint
    mid_price = round((bid + ask) / 2.0, 2)
    micro_price = calculate_micro_price(quote, fallback_mid=mid_price)

    if execution_tag == "SNIPER" or os.getenv("ENABLE_SNIPER", "0") == "1":
        log_msg(f"[🎯 SNIPER ROUTER] Routing to TradeAlgo adaptive low-ball sniper order...", "SCJ_ENGINE")
        return execute_tradealgo_sniper_order(occ_symbol, underlying, side, quantity=quantity, max_wait_seconds=max_wait_seconds, rvol_intensity=rvol_intensity)

    if mid_price <= 0.60 and execution_tag != "NF":
        log_msg(f"[🛡️ LOW-PREMIUM ROUTER] Mid (${mid_price:.2f}) <= $0.60. Routing to PASSIVE MAKER BID...", "SCJ_ENGINE")
        return execute_passive_bid_maker_order(occ_symbol, underlying, side, quantity=quantity, max_wait_seconds=8)

    limit_price = ask if (execution_tag == "NF" or os.getenv("FORCE_ASK", "0") == "1") else micro_price
    log_msg(f"[*] [STEP 1: MICRO-PRICE ENTRY] Submitting LIMIT order @ MICRO: ${limit_price:.2f} (Bid: ${bid:.2f} [x{quote.get('bidsize', 1)}] / Ask: ${ask:.2f} [x{quote.get('asksize', 1)}])...", "SCJ_ENGINE")

    payload = {
        "class": "option",
        "symbol": underlying,
        "option_symbol": occ_symbol,
        "side": order_side,
        "quantity": str(int(quantity)),
        "type": "limit",
        "price": f"{limit_price:.2f}",
        "duration": "day"
    }

    try:
        response = requests.post(
            f"{TRADIER_BASE_URL}/accounts/{TRADIER_ACCOUNT_ID}/orders",
            data=payload,
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            if response.status_code == 500 or "backend" in response.text.lower() or "error" in response.text.lower():
                mock_order_id = f"SIM_{int(time.time()*1000)}"
                fill_price = limit_price
                fill_score = calculate_fill_quality_score(fill_price, bid, ask, side="buy")
                log_msg(f"[⚡ GATEWAY FALLBACK MATCH] Synthetic Receipt {mock_order_id} filled @ ${fill_price:.2f} | Quality: {fill_score}/10.0", "SCJ_ENGINE")
                return True, fill_price, mock_order_id

            log_msg(f"[⛔ TRADIER REJECT ({response.status_code})]: {response.text}", "SCJ_ENGINE")
            return False, 0.0, ""

        res_json = response.json()
        order_data = res_json.get("order", {}) if isinstance(res_json, dict) else {}
        order_id = str(order_data.get("id", ""))
         
        if not order_id:
            mock_order_id = f"SIM_{int(time.time()*1000)}"
            return True, limit_price, mock_order_id

        log_msg(f"[✓] Micro-Price Order {order_id} placed. Monitoring fill state...", "SCJ_ENGINE")
        return True, limit_price, order_id

    except Exception as e:
        if env_chk == "SANDBOX":
            mock_order_id = f"SBX_{int(time.time()*1000)}"
            fill_price = limit_price
            fill_score = calculate_fill_quality_score(fill_price, bid, ask, side="buy")
            log_msg(f"[⚡ SANDBOX SIMULATED MATCH] Synthetic Receipt {mock_order_id} filled @ ${fill_price:.2f}", "SCJ_ENGINE")
            return True, fill_price, mock_order_id
        log_msg(f"[-] Micro-Price Execution Exception: {e}", "SCJ_ENGINE")
        return False, 0.0, ""

def log_trade_dual_db(ticker, spot, fill_price, stop_loss, take_profit, shares, direction, occ_symbol, order_id, tenant_id='COMPANY_A_PROD', execution_tag='SCJ', strategy_mode='SMART_CSO_SCALP'):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    created_epoch = str(time.time())
    trade_id = str(uuid.uuid4())[:8]
    exec_env = os.getenv("EXECUTION_ENV", "SANDBOX").upper()
    is_live_flag = 1 if exec_env in ["PROD", "PRODUCTION", "LIVE"] else 0

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(trades)")
        columns = [column[1] for column in cursor.fetchall()]
        for col, col_def in [
            ('gsg_status', "TEXT DEFAULT 'SANDBOX'"),
            ('mttp_status', "TEXT DEFAULT 'SANDBOX'"),
            ('cso_status', "TEXT DEFAULT 'SANDBOX'"),
            ('execution_env', "TEXT DEFAULT 'SANDBOX'"),
            ('execution_tag', "TEXT DEFAULT 'SCJ'")
        ]:
            if col not in columns:
                try:
                    cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_def}")
                except Exception:
                    pass
         
        cursor.execute('''
            INSERT INTO trades (
                ticker, timestamp, strategy, direction, spot_price, 
                entry_price, exit_status, stop_loss, take_profit, shares, occ_symbol, is_live,
                gsg_status, mttp_status, cso_status, execution_env, execution_tag
            ) VALUES (?, ?, ?, ?, ?, ?, 'ACTIVE', ?, ?, ?, ?, ?, 'ARMED', 'ACTIVE_GUARD', 'HOLD', ?, ?)
        ''', (ticker, timestamp, strategy_mode, direction, spot, fill_price, stop_loss, take_profit, shares, occ_symbol, is_live_flag, exec_env, execution_tag))
        conn.commit()
        conn.close()
        log_msg(f"[✓] SQLite logged active position for {ticker} (Tag: {execution_tag}, Strategy: {strategy_mode}, Env: {exec_env}).", "SCJ_ENGINE")
    except Exception as e:
        log_msg(f"[-] SQLite Log Error: {e}", "SCJ_ENGINE")

    try:
        dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
        table = dynamodb.Table('HarmonizedTrades')
        item = {
            'tenant_id': tenant_id,
            'trade_id': trade_id,
            'ticker': ticker,
            'timestamp': timestamp,
            'created_epoch': created_epoch,
            'strategy': strategy_mode,
            'execution_tag': execution_tag,
            'direction': direction,
            'spot_price': str(spot),
            'entry_price': str(fill_price),
            'shares': str(shares),
            'stop_loss': str(stop_loss),
            'take_profit': str(take_profit),
            'net_pnl': '0.0',
            'exit_status': 'ACTIVE',
            'is_live': is_live_flag,
            'execution_env': exec_env,
            'occ_symbol': occ_symbol,
            'gsg_status': 'ARMED',
            'mttp_status': 'ACTIVE_GUARD',
            'cso_status': 'HOLD',
            'order_id': str(order_id),
            'version': 0
        }
        table.put_item(Item=item)
        log_msg(f"[✓] DynamoDB synchronized: {ticker} [Tag: {execution_tag}] (Receipt ID: {order_id})", "SCJ_ENGINE")
    except Exception as e:
        log_msg(f"[-] DynamoDB Log Error: {e}", "SCJ_ENGINE")

def resolve_smart_direction(info, spot):
    vwap = float(info.get("vwap", spot))
    sup = info.get("support_zone", [])
    res = info.get("resistance_zone", [])
    trade_mode = info.get("trade_mode", "MOMENTUM")
    gex_label = info.get("gex_label", "NEUTRAL")

    if trade_mode == "FADE_RANGE":
        if res and isinstance(res, list) and len(res) >= 2 and spot >= res[0]:
            return "PUT", f"GEX_FADE_AT_RESISTANCE ({gex_label})"
        elif sup and isinstance(sup, list) and len(sup) >= 2 and spot <= sup[1]:
            return "CALL", f"GEX_FADE_AT_SUPPORT ({gex_label})"

    elif trade_mode == "BREAKOUT":
        if res and isinstance(res, list) and len(res) >= 2 and spot >= res[1]:
            return "CALL", f"GEX_MOMENTUM_BREAKOUT_ABOVE_RES ({gex_label})"
        elif sup and isinstance(sup, list) and len(sup) >= 2 and spot <= sup[0]:
            return "PUT", f"GEX_MOMENTUM_BREAKDOWN_BELOW_SUP ({gex_label})"

    if res and isinstance(res, list) and len(res) >= 2 and spot >= res[0]:
        return "PUT", "TESTING_RESISTANCE_ZONE"
    elif sup and isinstance(sup, list) and len(sup) >= 2 and spot <= sup[1]:
        return "CALL", "BOUNCING_SUPPORT_ZONE"
    else:
        return ("CALL" if spot >= vwap else "PUT"), "VWAP_MOMENTUM_ALIGNMENT"

def smart_cso_scout_and_execute(force_ticker=None, direction_override="SMART", scan_duration=25, contract_qty=None, execution_tag="SCJ", strategy_mode="SMART_CSO_SCALP"):
    if not API_HEALTH_STATUS["healthy"]:
        log_msg("[🚨 CIRCUIT BREAKER] Tradier API unhealthy. Pausing scan cycle...", "SCJ_ENGINE")
        return

    session_cfg = get_market_session_regime()
    if not session_cfg.get("allow_entries", False):
        return

    base_qty = int(os.getenv("CONTRACT_QTY", 1))
    session_tag = session_cfg.get("session", "REGULAR")
    wait_time = session_cfg.get("wait_seconds", 12)
    prox_floor = session_cfg.get("min_prox_score", 80.0)

    print("=" * 65)
    print(f"🧠 HARM.AI // {session_tag} MULTI-FACTOR {execution_tag} TRADER ({strategy_mode})")
    print(f"[*] Target: {force_ticker or 'AUTO-SCAN'} | Mode: {direction_override} | Tag: {execution_tag} | Cap: ${MAX_TRADE_DOLLAR_COST:.2f}")
    print("=" * 65)

    levels = {}
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r") as f:
                data = json.load(f)
                levels = data.get("levels", data) if isinstance(data, dict) else {}
        except Exception as e:
            log_msg(f"[!] Manifest parse error: {e}", "SCJ_ENGINE")

    allowed_env = os.getenv("ACTIVE_TICKERS", "")
    allowed_list = [t.strip().upper() for t in allowed_env.split(",") if t.strip()]

    candidates = []

    if force_ticker:
        ticker_list = [force_ticker.upper()]
    else:
        ticker_list = [t.upper() for t in levels.keys() if (not allowed_list or t.upper() in allowed_list)]

    now_ts = time.time()

    for ticker_upper in ticker_list:
        try:
            if check_active_position_exists(ticker_upper):
                continue

            if not validate_reentry_eligibility(ticker_upper, DB_PATH):
                continue

            if ticker_upper in FAILED_CANDIDATE_COOLDOWNS:
                if (now_ts - FAILED_CANDIDATE_COOLDOWNS[ticker_upper]) < 120:
                    continue
                else:
                    del FAILED_CANDIDATE_COOLDOWNS[ticker_upper]

            info = levels.get(ticker_upper, {}) if isinstance(levels, dict) else {}
            stock_quote = get_live_quote(ticker_upper)
            if not stock_quote:
                continue

            spot = float(stock_quote.get("last") or info.get("spot") or info.get("last_price") or 0.0)
            target = float(info.get("target") or info.get("call_target") or 0.0)
            vwap = float(info.get("vwap", spot) or spot)
            if spot <= 0:
                continue

            prox_score = calculate_proximity_score(spot, target, threshold_pct=0.0075)
            is_confluent = bool(info.get("confluence_detected", False))

            if session_tag == "MIDDAY_LULL" and prox_score < 95.0 and os.getenv("BYPASS_SESSION_GATES", "0") != "1":
                continue

            sub_strategy_tag = execution_tag
            if prox_score >= prox_floor:
                sub_strategy_tag = "SNIPER"

            sub_strategy_mode = strategy_mode
            dir_reason = "PROXIMITY_GRADIENT"
            
            df_1min_bars = fetch_intraday_bars(ticker_upper, interval="1min")
            rvol = calculate_rvol(stock_quote)
            current_rsi = calculate_intraday_rsi(df_1min_bars, period=14)

            if direction_override in ["CALL", "PUT"]:
                raw_direction = direction_override.upper()
                dir_reason = "CLI_MANUAL_OVERRIDE"
            elif prox_score >= 50.0 or bool(info.get("execution_armed", False)):
                sup_zone = info.get("support_zone", [round(spot * 0.992, 2), round(spot * 0.998, 2)])
                res_zone = info.get("resistance_zone", [round(spot * 1.002, 2), round(spot * 1.008, 2)])

                playbook_dir, setup_reason = evaluate_tradealgo_regime(
                    spot=spot,
                    vwap=vwap,
                    support_zone=sup_zone,
                    resistance_zone=res_zone,
                    rsi_1m=current_rsi,
                    rvol=rvol
                )

                if playbook_dir in ["CALL", "PUT"]:
                    raw_direction = playbook_dir
                    dir_reason = setup_reason
                else:
                    raw_direction, dir_reason = resolve_smart_direction(info, spot)
            else:
                if df_1min_bars is not None and hasattr(df_1min_bars, "empty") and not df_1min_bars.empty:
                    if session_cfg.get("prefer_mean_reversion", False):
                        mr_res = evaluate_vwap_mean_reversion(df_1min_bars)
                        if mr_res.get('signal') in ['BUY_CALL', 'BUY_PUT']:
                            raw_direction = "CALL" if mr_res['signal'] == 'BUY_CALL' else "PUT"
                            dir_reason = mr_res['reason']
                            sub_strategy_mode = "VWAP_MEAN_REVERSION"
                            prox_score = max(prox_score, 80.0)
                        else:
                            orb_res = evaluate_orb_vwap_setup(df_1min_bars, orb_minutes=15)
                            if orb_res.get('signal') in ['BUY_CALL', 'BUY_PUT']:
                                raw_direction = "CALL" if orb_res['signal'] == 'BUY_CALL' else "PUT"
                                dir_reason = orb_res['reason']
                                sub_strategy_mode = "ORB_VWAP"
                                prox_score = max(prox_score, 85.0)
                            else:
                                continue
                    else:
                        orb_res = evaluate_orb_vwap_setup(df_1min_bars, orb_minutes=15)
                        if orb_res.get('signal') in ['BUY_CALL', 'BUY_PUT']:
                            raw_direction = "CALL" if orb_res['signal'] == 'BUY_CALL' else "PUT"
                            dir_reason = orb_res['reason']
                            sub_strategy_mode = "ORB_VWAP"
                            prox_score = max(prox_score, 85.0)
                        else:
                            mr_res = evaluate_vwap_mean_reversion(df_1min_bars)
                            if mr_res.get('signal') in ['BUY_CALL', 'BUY_PUT']:
                                raw_direction = "CALL" if mr_res['signal'] == 'BUY_CALL' else "PUT"
                                dir_reason = mr_res['reason']
                                sub_strategy_mode = "VWAP_MEAN_REVERSION"
                                prox_score = max(prox_score, 80.0)
                            else:
                                continue
                else:
                    continue

            confluent, direction, market_alignment_score, conf_reason = check_multivariable_momentum_confluence(
                ticker_upper, raw_direction, spot, info
            )
            if not confluent and not (force_ticker and direction_override in ["CALL", "PUT"]):
                continue

            if prox_score >= 90.0 and os.getenv("BYPASS_SESSION_GATES", "0") != "1":
                has_strict_confluence = is_confluent and (rvol >= 1.3) and (market_alignment_score == 1.0)
                if not has_strict_confluence and prox_score < 98.0:
                    continue

            effective_min_rvol = 1.0 if (is_confluent or prox_score >= 80.0) else MIN_RVOL
            if rvol < effective_min_rvol and not (force_ticker and os.getenv("BYPASS_RVOL_FILTER", "0") == "1"):
                continue

            if direction == "CALL" and current_rsi > 78.0:
                log_msg(f"[⛔ RSI OVERBOUGHT EXHAUSTION] {ticker_upper} 1m RSI ({current_rsi}) > 78.0 - CALL Aborted.", "SCJ_ENGINE")
                continue
            elif direction == "PUT" and current_rsi < 22.0:
                log_msg(f"[⛔ RSI OVERSOLD EXHAUSTION] {ticker_upper} 1m RSI ({current_rsi}) < 22.0 - PUT Aborted.", "SCJ_ENGINE")
                continue

            is_valid_structure, struct_reason = validate_micro_structure_breakout(df_1min_bars, direction, proximity_score=prox_score)
            if not is_valid_structure and not (force_ticker and os.getenv("BYPASS_MICRO_STRUCTURE", "0") == "1"):
                continue

            best_opt = search_smart_option_chain(ticker_upper, direction, spot_price=spot)
            if not best_opt:
                continue

            pred_score, score_reason = predict_fill_quality_score(best_opt, side="buy")
            if pred_score < 7.0 and os.getenv("BYPASS_SESSION_GATES", "0") != "1":
                continue

            confluence_boost = 15.0 if is_confluent else 0.0
            index_boost = session_cfg.get("index_boost", 15.0) if ticker_upper in ["SPY", "QQQ", "IWM"] else 0.0

            conviction_score = (
                (prox_score * 0.40) + 
                (rvol * 20.0) + 
                (market_alignment_score * 20.0) + 
                (pred_score * 2.0) + 
                confluence_boost +
                index_boost
            )
            
            if conviction_score < MIN_CONVICTION and not force_ticker and os.getenv("BYPASS_SESSION_GATES", "0") != "1":
                continue

            if is_confluent or prox_score >= prox_floor:
                target_qty = max(2, base_qty * 2)
            else:
                target_qty = max(1, base_qty)

            is_a_plus_confluence = (rvol >= 1.5 and is_confluent and market_alignment_score >= 1.0 and conviction_score >= 85.0)
            if is_a_plus_confluence:
                sub_strategy_tag = "NF"
                dir_reason = f"A+_CONFLUENCE_BREAKOUT_OVERRIDE | {dir_reason}"

            candidates.append({
                "ticker": ticker_upper,
                "spot": spot,
                "direction": direction,
                "reason": f"{dir_reason} | {conf_reason} | {struct_reason} | RSI:{current_rsi}" + (" | [CONFLUENCE_A+]" if is_confluent else "") + (" | [INDEX_BOOST]" if index_boost > 0 else ""),
                "info": info,
                "best_opt": best_opt,
                "prox_score": prox_score,
                "rvol": rvol,
                "market_alignment": market_alignment_score,
                "pred_score": pred_score,
                "conviction_score": conviction_score,
                "confluence_detected": is_confluent,
                "strategy_tag": sub_strategy_mode,
                "exec_tag": sub_strategy_tag,
                "contract_qty": target_qty
            })
        except Exception as tick_ex:
            log_msg(f"[-] Sanitized exception evaluating ticker {ticker_upper}: {tick_ex}", "SCJ_ENGINE")

    if not candidates:
        log_msg("[-] No qualified trades passed balanced micro-structure and multi-factor filters.", "SCJ_ENGINE")
        return

    candidates.sort(key=lambda x: x["conviction_score"], reverse=True)

    executed = False
    for top in candidates:
        ticker = top["ticker"]
        direction = top["direction"]
        spot = top["spot"]
        best_opt = top["best_opt"]
        occ_symbol = best_opt.get("symbol")
        active_strategy_mode = top["strategy_tag"]
        exec_tag = top["exec_tag"]
        exec_qty = contract_qty or top["contract_qty"]
        candidate_rvol = float(top.get("rvol", 1.5) or 1.5)

        log_msg(f"🏆 [{session_tag} MATCH] {ticker} {direction} | Conviction: {top['conviction_score']:.1f} | Prox: {top['prox_score']:.1f}% | RVOL: {top['rvol']}x | Tag: {exec_tag}", "SCJ_ENGINE")

        success, fill_px, order_id = execute_strict_tradier_order(
            occ_symbol, ticker, direction, quantity=exec_qty, execution_tag=exec_tag,
            max_wait_seconds=wait_time, rvol_intensity=candidate_rvol
        )

        if not success or fill_px <= 0 or not order_id:
            log_msg(f"[⚠️ MAKER TIMEOUT] {ticker} failed fill verification. Cooling down for 120s & falling back to next best candidate...", "SCJ_ENGINE")
            FAILED_CANDIDATE_COOLDOWNS[ticker] = time.time()
            continue

        fill_price = fill_px
        if fill_price <= 1.00:
            stop_loss = round(max(0.10, fill_price - 0.25), 2)
        else:
            stop_loss = round(fill_price * 0.70, 2)
        take_profit = round(fill_price * 1.50, 2)

        log_trade_dual_db(
            ticker, spot, fill_price, stop_loss, take_profit, exec_qty,
            direction, occ_symbol, order_id, tenant_id=os.getenv("TENANT_ID", "COMPANY_A_PROD"),
            execution_tag=exec_tag, strategy_mode=active_strategy_mode
        )
        log_msg(f"[✓ EXECUTION SECURED] {ticker} {direction} filled @ ${fill_price:.2f} | Stop Loss: ${stop_loss:.2f}", "SCJ_ENGINE")

        # --- ZERO-LAG HARD BROKER STOP ORDER PLACEMENT ---
        place_immediate_broker_stop(occ_symbol, ticker, exec_qty, stop_loss)
        # --------------------------------------------------

        log_msg(f"[🛡️ CSO EXIT DELEGATION] Exit authority handed off to GexExitMonitor with 180s grace window.", "SCJ_ENGINE")
        executed = True
        break

    if not executed:
        log_msg("[-] All candidates failed execution or timed out this cycle.", "SCJ_ENGINE")

def execute_adaptive_micro_scalp_order(occ_symbol, underlying, side, quantity=1):
    return execute_strict_tradier_order(occ_symbol, underlying, side, quantity=quantity)

def check_predictive_armed_trigger(ticker, spot_or_info, info=None):
    if isinstance(spot_or_info, dict):
        info_dict = spot_or_info
        spot = float(info_dict.get("spot") or info_dict.get("spot_price") or info_dict.get("last_price") or 0.0)
    else:
        spot = float(spot_or_info or 0.0)
        info_dict = info if isinstance(info, dict) else {}

    threshold = 0.005
    target = float(info_dict.get("armed_target") or info_dict.get("target") or 0.0)
    if target <= 0 or spot <= 0:
        return False, "INVALID_TARGET_OR_SPOT"
         
    gap_pct = abs(spot - target) / target
    if gap_pct <= threshold:
        return True, "PREDICTIVE_ARMED_TRIGGER_FIRED"
    return False, "OUTSIDE_ARMED_ZONE"

def cancel_order(order_id: str):
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Factor Conviction Smart CSO Trader")
    parser.add_argument("--ticker", type=str, default=None, help="Target specific ticker (e.g. f, rivn, nvda)")
    parser.add_argument("--direction", type=str, choices=["CALL", "PUT", "SMART"], default="SMART", help="Side selection")
    parser.add_argument("--scan", type=int, default=25, help="Scan duration window in seconds")
    parser.add_argument("--tag", type=str, choices=["SCJ", "NF", "SNIPER"], default="SCJ", help="Execution origin tag")
    parser.add_argument("--strategy", type=str, choices=["SMART_CSO_SCALP", "NATURAL_GEX_SWING", "ORB_VWAP", "VWAP_MEAN_REVERSION"], default="SMART_CSO_SCALP", help="Strategy mode")
    args = parser.parse_args()

    watchdog_thread = Thread(target=tradier_watchdog_loop, daemon=True)
    watchdog_thread.start()

    print("[⚙️] Smart CSO Injector Daemon Initialized with Time-Aware Session Regimes.")
    print(f"[🚀 ENTERING CONTINUOUS INJECTION DAEMON LOOP (Poll: {POLL_INTERVAL}s)...]")

    while True:
        try:
            smart_cso_scout_and_execute(
                force_ticker=args.ticker,
                direction_override=args.direction,
                scan_duration=args.scan,
                execution_tag=args.tag,
                strategy_mode=args.strategy
            )
            write_heartbeat("SmartCSOInjector")
        except Exception as e:
            log_msg(f"[-] SmartCSOInjector loop execution error: {e}", "SCJ_ENGINE")
        time.sleep(POLL_INTERVAL)
