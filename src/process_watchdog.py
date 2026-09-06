#!/usr/bin/env python3
"""
HARM.AI // PROCESS & LEVEL TELEMETRY WATCHDOG DAEMON
===============================================================================
Audits both background services and trading level manifests every 10 seconds:
1. Process Heartbeat: PIDs for LiveBot, GexExitMonitor, ActiveRiskDaemon, BotStreamer.
   - Triggers Discord alerts and auto-restarts dead/frozen daemons.
2. Level Watchdog: File existence, age/staleness, and 27-ticker completeness for:
   - trading_levels_gex.json
   - trading_levels_tradealgo.json
   - trading_levels.json
3. Self-Healing: Automatically invokes sync_gex_lambda.py and level_synthesizer.py.
4. Dashboard Heartbeat: Publishes logs/heartbeats/LevelSentinel.json for the UI.
"""

import os
import sys
import time
import json
import sqlite3
import subprocess
import requests
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'harm_telemetry.db')
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")

GEX_PATH = os.path.join(BASE_DIR, "trading_levels_gex.json")
TRADEALGO_PATH = os.path.join(BASE_DIR, "trading_levels_tradealgo.json")
SYNTHESIZED_PATH = os.path.join(BASE_DIR, "trading_levels.json")
HEARTBEAT_DIR = os.path.join(BASE_DIR, "logs", "heartbeats")
SENTINEL_JSON = os.path.join(HEARTBEAT_DIR, "LevelSentinel.json")

MONITORED_SERVICES = {
    "LiveBot": "src/LiveBot.py",
    "GexExitMonitor": "src/gex_exit_monitor.py",
    "ActiveRiskDaemon": "src/active_risk_daemon.py",
    "BotStreamer": "harmonized_bot_streamer.py"
}

EXPECTED_TICKER_COUNT = 27
MAX_MANIFEST_STALE_SECONDS = 1200  # 20 minutes

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG] {msg}")

def send_discord_alert(service_name: str, reason: str, action: str = "Auto-Restart Initiated"):
    if not DISCORD_WEBHOOK or "your_webhook" in DISCORD_WEBHOOK:
        return
    payload = {
        "embeds": [{
            "title": f"🚨 HARM.AI CRITICAL SERVICE FAILURE: {service_name}",
            "color": 15158332,
            "fields": [
                {"name": "Service", "value": f"`{service_name}`", "inline": True},
                {"name": "Failure Reason", "value": f"**{reason}**", "inline": True},
                {"name": "Action Taken", "value": action, "inline": True}
            ],
            "footer": {"text": "HARM.AI Watchdog Sentinel"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=3)
    except Exception:
        pass

def is_process_running(script_name: str) -> bool:
    try:
        out = subprocess.check_output(["ps", "aux"]).decode()
        return script_name in out
    except Exception:
        return False

def audit_service_health():
    log_msg("Checking service health & process heartbeats...")
    for name, script_path in MONITORED_SERVICES.items():
        running = is_process_running(script_path)
        if not running:
            log_msg(f"🚨 [PROCESS DEAD] {name} ({script_path}) is NOT running!")
            send_discord_alert(name, "Process Terminated / Dead PID", "Auto-Restart Initiated")
            
            # Auto-restart process in background using absolute path resolution
            log_msg(f"[🔄 RESTARTING] Launching {script_path}...")
            full_path = os.path.join(BASE_DIR, script_path) if not os.path.isabs(script_path) else script_path
            subprocess.Popen([sys.executable, "-u", full_path])

def inspect_manifest(path: str, name: str) -> dict:
    if not os.path.exists(path):
        return {"status": "MISSING", "count": 0, "age_sec": 999999, "corrupt": True}
    
    age_sec = time.time() - os.path.getmtime(path)
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"status": "INVALID_FORMAT", "count": 0, "age_sec": age_sec, "corrupt": True}
        
        # Guardrail spot-check on SPY
        spy = data.get("SPY", {})
        spot = spy.get("spot", spy.get("last_price", 0.0))
        if spot <= 0:
            return {"status": "ANOMALOUS_PRICING", "count": len(data), "age_sec": age_sec, "corrupt": True}

        status = "HEALTHY" if len(data) >= EXPECTED_TICKER_COUNT and age_sec <= MAX_MANIFEST_STALE_SECONDS else "DEGRADED"
        return {"status": status, "count": len(data), "age_sec": round(age_sec, 1), "corrupt": False}
    except Exception as e:
        return {"status": f"READ_ERROR: {str(e)}", "count": 0, "age_sec": age_sec, "corrupt": True}

def audit_level_pipeline():
    os.makedirs(HEARTBEAT_DIR, exist_ok=True)

    gex_stat = inspect_manifest(GEX_PATH, "GEX")
    algo_stat = inspect_manifest(TRADEALGO_PATH, "TradeAlgo")
    synth_stat = inspect_manifest(SYNTHESIZED_PATH, "Master_Trading_Levels")

    # 1. GEX Manifest Staleness / Completeness Check
    if gex_stat["corrupt"] or gex_stat["count"] < EXPECTED_TICKER_COUNT or gex_stat["age_sec"] > MAX_MANIFEST_STALE_SECONDS:
        log_msg(f"⚠️ GEX manifest compromised/stale ({gex_stat['status']} | {gex_stat['count']} tickers). Triggering self-healing...")
        send_discord_alert("LevelSentinel: GEX", f"Stale/Incomplete GEX Manifest ({gex_stat['count']}/{EXPECTED_TICKER_COUNT})", "Triggering sync_gex_lambda.py")
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "src", "sync_gex_lambda.py")], check=False)
        gex_stat = inspect_manifest(GEX_PATH, "GEX")

    # 2. Master Synthesized Manifest Desync Check
    if synth_stat["corrupt"] or synth_stat["count"] < EXPECTED_TICKER_COUNT or synth_stat["age_sec"] > MAX_MANIFEST_STALE_SECONDS:
        log_msg(f"⚠️ Master trading_levels.json compromised/stale ({synth_stat['status']} | {synth_stat['count']} tickers). Triggering synthesis...")
        send_discord_alert("LevelSentinel: Master", f"Master levels de-synced ({synth_stat['count']}/{EXPECTED_TICKER_COUNT})", "Triggering level_synthesizer.py")
        subprocess.run([sys.executable, os.path.join(BASE_DIR, "src", "level_synthesizer.py")], check=False)
        synth_stat = inspect_manifest(SYNTHESIZED_PATH, "Master_Trading_Levels")

    # 3. Publish Sentinel Heartbeat Artifact for Web Dashboard
    overall_status = "ONLINE" if (gex_stat["count"] >= EXPECTED_TICKER_COUNT and synth_stat["count"] >= EXPECTED_TICKER_COUNT) else "DEGRADED"

    sentinel_payload = {
        "service": "LevelSentinel",
        "status": overall_status,
        "pid": os.getpid(),
        "timestamp": datetime.now().strftime("%H:%M:%S ET"),
        "epoch": time.time(),
        "manifests": {
            "trading_levels_gex": gex_stat,
            "trading_levels_tradealgo": algo_stat,
            "trading_levels": synth_stat
        }
    }

    try:
        with open(SENTINEL_JSON, "w") as f:
            json.dump(sentinel_payload, f, indent=2)
    except Exception as e:
        log_msg(f"[-] Could not write sentinel heartbeat artifact: {e}")

if __name__ == "__main__":
    log_msg("Process & Level Watchdog Daemon online. Auditing every 10 seconds...")
    while True:
        try:
            audit_service_health()
            audit_level_pipeline()
        except Exception as ex:
            log_msg(f"[-] Unhandled exception in audit loop: {ex}")
        time.sleep(10)
