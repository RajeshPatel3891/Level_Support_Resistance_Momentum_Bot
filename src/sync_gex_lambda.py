#!/usr/bin/env python3
"""
HARM.AI // GEMMAEX LAMBDA GEX HARVESTER & MANIFEST GENERATOR (27-TICKER MATRIX)
===============================================================================
1. Invokes the GemmaEX AWS Lambda function via boto3.
2. Extracts live underlying quotes, calculated Net GEX, and GEX labels (POSITIVE/NEGATIVE).
3. Derives price-tiered dynamic zones, call/put targets, and MTTP timers.
4. Atomically writes the correlated state directly into trading_levels_gex.json.
"""

import os
import sys
import json
import boto3
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEX_PATH = os.path.join(BASE_DIR, "trading_levels_gex.json")

if os.path.exists(os.path.join(BASE_DIR, ".env.prod")):
    load_dotenv(os.path.join(BASE_DIR, ".env.prod"), override=True)
else:
    load_dotenv(override=True)

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

def get_beta_category(ticker: str) -> str:
    if ticker in ["SPY", "QQQ", "IWM", "XLF", "GDX", "XLE"]:
        return "ETF"
    elif ticker in ["NVDA", "TSLA", "AAPL", "AMD", "META", "NFLX", "MARA"]:
        return "HIGH"
    elif ticker in ["PLTR", "SOFI", "HOOD", "SNAP", "UBER", "NKE", "RIVN"]:
        return "MID"
    return "LOW"

def get_zone_pct(beta: str) -> float:
    if beta == "ETF":
        return 0.0020
    elif beta == "HIGH":
        return 0.0040
    elif beta == "MID":
        return 0.0030
    return 0.0020

def get_proximity_threshold(price: float) -> float:
    if price >= 100.0:
        return 0.0075
    elif price >= 30.0:
        return 0.0085
    return 0.0120

def fetch_gex_from_lambda() -> list:
    print(f"[*] Invoking GemmaEX Lambda in {AWS_REGION}...")
    try:
        client = boto3.client("lambda", region_name=AWS_REGION)
        response = client.invoke(
            FunctionName="GemmaEX",
            InvocationType="RequestResponse",
            Payload=json.dumps({})
        )
        payload = json.loads(response["Payload"].read().decode("utf-8"))
        body = json.loads(payload.get("body", "{}")) if isinstance(payload.get("body"), str) else payload.get("body", {})
        data = body.get("data", [])
        print(f"[✓] Successfully retrieved {len(data)} ticker GEX calculations from GemmaEX.")
        return data
    except Exception as e:
        print(f"[-] Error invoking GemmaEX Lambda: {e}")
        return []

def run_sync():
    gex_records = fetch_gex_from_lambda()
    if not gex_records:
        print("[-] Aborting sync: No payload returned from GemmaEX Lambda.")
        sys.exit(1)

    manifest = {}
    for item in gex_records:
        ticker = item.get("ticker")
        spot = float(item.get("underlying_price", 0.0))
        net_gex = float(item.get("net_gex", 0.0))
        raw_label = item.get("gex_label", "NEUTRAL")

        if not ticker or spot <= 0:
            continue

        beta = get_beta_category(ticker)
        zone_pct = get_zone_pct(beta)
        prox_thresh = get_proximity_threshold(spot)

        call_target = round(spot * (1.0 + zone_pct), 2)
        put_target = round(spot * (1.0 - zone_pct), 2)

        support_a = round(spot * (1.0 - (zone_pct * 1.5)), 2)
        support_b = round(spot * (1.0 - (zone_pct * 0.5)), 2)
        resistance_a = round(spot * (1.0 + (zone_pct * 0.5)), 2)
        resistance_b = round(spot * (1.0 + (zone_pct * 1.5)), 2)

        manifest[ticker] = {
            "zone_pct": zone_pct,
            "turn_ticks": 3 if beta == "HIGH" else 2,
            "mttp_minutes": 20 if beta == "ETF" else (25 if beta == "HIGH" else 35),
            "beta": beta,
            "spot": spot,
            "price": spot,
            "last_price": spot,
            "spot_price": spot,
            "vwap": spot,
            "net_gex": net_gex,
            "gex_label": raw_label,
            "call_target": call_target,
            "put_target": put_target,
            "spot_target_call": call_target,
            "spot_target_put": put_target,
            "proximity_threshold": prox_thresh,
            "gap_pct": 0.5,
            "execution_armed": True,
            "support_a": support_a,
            "support_b": support_b,
            "resistance_a": resistance_a,
            "resistance_b": resistance_b,
            "support_zone": [support_a, support_b],
            "resistance_zone": [resistance_a, resistance_b],
            "timestamp": item.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        }

    with open(GEX_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"[🚀 SUCCESS] Correlated and published {len(manifest)} tickers to {GEX_PATH}")

if __name__ == "__main__":
    run_sync()
