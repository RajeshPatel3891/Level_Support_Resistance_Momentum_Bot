#!/usr/bin/env python3
"""
HARM.AI // OPTION CONTRACT SPREAD QUALIFIER
===============================================================================
Queries live Tradier quotes for active OPTION contracts and evaluates if they
pass the 4% relative spread rule.
"""

import os
import json
import requests
from dotenv import load_dotenv

if os.path.exists('.env.prod'):
    load_dotenv('.env.prod', override=True)
else:
    load_dotenv(override=True)

def get_tradier_token():
    token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN') or os.getenv('TRADIER_ACCESS_TOKEN')
    if token:
        return token
    if os.path.exists('system_config.json'):
        try:
            with open('system_config.json', 'r') as f:
                cfg = json.load(f)
                return cfg.get('tradier_access_token', cfg.get('TRADIER_ACCESS_TOKEN', ''))
        except Exception:
            pass
    return ''

TRADIER_TOKEN = get_tradier_token()
BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1").rstrip('/')

# Active Option Contracts Sample
OPTION_CONTRACTS = [
    "SPY260904C00560000",
    "QQQ260904C00480000",
    "NVDA260904C00130000",
    "TSLA260904C00210000",
    "F260904C00012000",
    "AAL260904C00011000",
    "HOOD260904C00020000"
]

def evaluate_spread_qualification():
    if not TRADIER_TOKEN:
        print("[!] Tradier token missing across .env, .env.prod, and system_config.json.")
        return

    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    
    print("=" * 95)
    print("📊 HARM.AI // OPTION CONTRACT 4% SPREAD LIQUIDITY REPORT")
    print("=" * 95)
    print(f"{'OPTION CONTRACT':<22} | {'BID':<7} | {'ASK':<7} | {'MID':<7} | {'SPREAD ($)':<10} | {'SPREAD (%)':<10} | {'STATUS'}")
    print("-" * 95)

    symbols_str = ",".join(OPTION_CONTRACTS)
    try:
        res = requests.get(f"{BASE_URL}/markets/quotes?symbols={symbols_str}", headers=headers, timeout=5)
        if res.status_code == 200:
            quotes = res.json().get('quotes', {}).get('quote', [])
            if isinstance(quotes, dict): quotes = [quotes]
            
            for q in quotes:
                symbol = q.get('symbol', 'N/A')
                bid = float(q.get('bid') or 0.0)
                ask = float(q.get('ask') or 0.0)
                mid = round((bid + ask) / 2.0, 2)
                
                if mid > 0:
                    spread_abs = round(ask - bid, 2)
                    spread_pct = round((spread_abs / mid) * 100.0, 2)
                    
                    if spread_pct <= 4.0 or (mid <= 0.50 and spread_abs <= 0.02):
                        status = "✅ QUALIFIED"
                    else:
                        status = "🔴 REJECTED (>4%)"

                    print(f"{symbol:<22} | ${bid:<6.2f} | ${ask:<6.2f} | ${mid:<6.2f} | ${spread_abs:<9.2f} | {spread_pct:<9.2f}% | {status}")
                else:
                    print(f"{symbol:<22} | Market Closed / Quote Book Empty")
    except Exception as e:
        print(f"[-] Error querying option contracts: {e}")

    print("=" * 95)

if __name__ == "__main__":
    evaluate_spread_qualification()
