print("--- SCRIPT STARTED ---")
# -*- coding: utf-8 -*-

import os
import json
import sys
import time
import urllib.request
import urllib.error
import requests
from datetime import datetime
from dotenv import load_dotenv
from src.HarmonizedDispatch import execute_trade

load_dotenv()

# Live Webhook Core
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
LEVELS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trading_levels.json')

CODE_BLOCK_INI_START = "```" + "ini\n"
CODE_BLOCK_END = "\n" + "```"

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def load_trading_levels():
    with open(LEVELS_FILE, 'r') as f:
        return json.load(f)

def update_resistance(new_resistance):
    """Programmatically updates the JSON file the monitor reads."""
    with open(LEVELS_FILE, 'r+') as f:
        data = json.load(f)
        # Update the level to trigger the breach
        if "levels" in data and "SPY" in data["levels"]:
            data["levels"]["SPY"]["human_tactical"]["tactical_resistance"] = [new_resistance]
            f.seek(0)
            json.dump(data, f, indent=4)
            f.truncate()
            log_msg(f"[*] Updated resistance to {new_resistance}")

def dispatch_alert_with_retry(payload):
    try:
        req = urllib.request.Request(DISCORD_WEBHOOK_URL, data=json.dumps(payload).encode('utf-8'), 
                                     headers={'User-Agent': 'HarmonizedSentryBot/1.2', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req): pass
        return True
    except Exception as e:
        log_msg(f"Webhook error: {e}"); return False

def simulate_breakout(symbol, level, direction="CALL"):
    payload = {"embeds": [{"title": "TEST ALERT", "description": f"Triggered {symbol} at {level}", "color": 3447003}]}
    
    # Debug 1: Discord Webhook
    print(f"[*] Attempting to send discord alert...")
    webhook_status = dispatch_alert_with_retry(payload)
    print(f"[*] Discord Webhook Status: {webhook_status}")

    if webhook_status:
        log_msg(f"[✓] Alert sent. Executing order...")
        
        # Debug 2: Execute Trade
        status, response = execute_trade(symbol, direction)
        print(f"[DEBUG] execute_trade returned status={status}, response={response}")
        
        log_msg(f"[?] Unified Execution Status: {status} | Response: {response}")

def run_simulation(set_resistance=None):
    # If a test resistance level is provided, inject it first
    if set_resistance:
        update_resistance(set_resistance)
        
    data = load_trading_levels()
    for symbol, config in data.get("levels", {}).items():
        if "human_tactical" in config and "breakout_trigger" in config["human_tactical"]:
            simulate_breakout(symbol, config["human_tactical"]["breakout_trigger"], "CALL")
            break

if __name__ == '__main__':
    # Usage: python3 simulate_alert.py [optional_resistance_level]
    target_res = float(sys.argv[1]) if len(sys.argv) > 1 else None
    run_simulation(set_resistance=target_res)
print("--- SCRIPT FINISHED ---")
