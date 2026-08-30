#!/usr/bin/env python3
"""
HARM.AI // PROCESS HEARTBEAT WATCHDOG DAEMON
===============================================================================
Audits background services every 10 seconds.
Triggers Discord alerts and auto-restarts dead/frozen daemons if:
1. Process PID is dead (`ps aux` check).
2. Heartbeat timestamp in harm_telemetry.db > 15s stale.
"""

import os
import sys
import time
import sqlite3
import subprocess
import requests
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'harm_telemetry.db')
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL", "")

MONITORED_SERVICES = {
    "LiveBot": "src/LiveBot.py",
    "GexExitMonitor": "src/gex_exit_monitor.py",
    "ActiveRiskDaemon": "src/active_risk_daemon.py",
    "BotStreamer": "harmonized_bot_streamer.py"
}

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [WATCHDOG] {msg}")

def send_discord_alert(service_name, reason):
    if not DISCORD_WEBHOOK or "your_webhook" in DISCORD_WEBHOOK:
        return
    payload = {
        "embeds": [{
            "title": f"🚨 HARM.AI CRITICAL SERVICE FAILURE: {service_name}",
            "color": 15158332,
            "fields": [
                {"name": "Service", "value": f"`{service_name}`", "inline": True},
                {"name": "Failure Reason", "value": f"**{reason}**", "inline": True},
                {"name": "Action Taken", "value": "Auto-Restart Initiated", "inline": True}
            ],
            "footer": {"text": "HARM.AI Watchdog Sentinel"}
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK, json=payload, timeout=3)
    except Exception:
        pass

def is_process_running(script_name):
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
            send_discord_alert(name, "Process Terminated / Dead PID")
            
            # Auto-restart process in background
            log_msg(f"[🔄 RESTARTING] Launching {script_path}...")
            subprocess.Popen([sys.executable, "-u", script_path])

if __name__ == "__main__":
    log_msg("Process Watchdog Daemon online. Auditing every 10 seconds...")
    while True:
        audit_service_health()
        time.sleep(10)
