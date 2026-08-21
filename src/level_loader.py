#!/usr/bin/env python3
"""
HARM.AI // CLOUD-FIRST S3 TRADING LEVEL LOADER & ENRICHMENT ENGINE (24-TICKER MATRIX)
===============================================================================
1. Fetches latest trading_levels.json from S3 bucket (harmonized-ai-telemetry-bucket).
2. Fallbacks to local disk if S3 is unreachable.
3. Enriches raw level payloads with ticker-specific Beta parameters (zone_pct, turn_ticks, mttp_minutes).
4. Atomically writes updates back to disk, memory cache, and S3.
"""

import os
import sys
import json
import time
import boto3
from dotenv import load_dotenv

# Load Environment
if os.path.exists(".env.prod"):
    load_dotenv(".env.prod", override=True)
else:
    load_dotenv(override=True)

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "harmonized-ai-telemetry-bucket")
S3_LEVELS_KEY = "config/trading_levels.json"
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
LOCAL_LEVELS_PATH = os.getenv("LEVELS_PATH", os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading_levels.json"))

CACHE_TTL = 300  # 5-minute intraday cache TTL
_CACHE = {"timestamp": 0, "data": {}}

# Complete 24-Ticker Beta Calibration Map
CONFIG_MAP = {
    # Index ETFs (Penny Spreads, Ultra High Liquidity)
    "SPY":   {"zone_pct": 0.0015, "turn_ticks": 2, "mttp_minutes": 20, "beta": "ETF"},
    "QQQ":   {"zone_pct": 0.0020, "turn_ticks": 2, "mttp_minutes": 20, "beta": "ETF"},
    "IWM":   {"zone_pct": 0.0025, "turn_ticks": 2, "mttp_minutes": 25, "beta": "ETF"},

    # High Beta / Mega-Cap Tech
    "NVDA":  {"zone_pct": 0.0040, "turn_ticks": 3, "mttp_minutes": 25, "beta": "HIGH"},
    "TSLA":  {"zone_pct": 0.0040, "turn_ticks": 3, "mttp_minutes": 25, "beta": "HIGH"},
    "AAPL":  {"zone_pct": 0.0040, "turn_ticks": 3, "mttp_minutes": 25, "beta": "HIGH"},
    "AMZN":  {"zone_pct": 0.0035, "turn_ticks": 3, "mttp_minutes": 25, "beta": "HIGH"},
    "GOOGL": {"zone_pct": 0.0030, "turn_ticks": 3, "mttp_minutes": 25, "beta": "HIGH"},
    "AMD":   {"zone_pct": 0.0040, "turn_ticks": 3, "mttp_minutes": 25, "beta": "HIGH"},
    "META":  {"zone_pct": 0.0045, "turn_ticks": 3, "mttp_minutes": 25, "beta": "HIGH"},
    "NFLX":  {"zone_pct": 0.0045, "turn_ticks": 3, "mttp_minutes": 25, "beta": "HIGH"},
    "PLTR":  {"zone_pct": 0.0030, "turn_ticks": 3, "mttp_minutes": 35, "beta": "MID"},

    # Mid/Low Beta & High-Liquidity Names
    "SOFI":  {"zone_pct": 0.0030, "turn_ticks": 3, "mttp_minutes": 35, "beta": "MID"},
    "F":     {"zone_pct": 0.0020, "turn_ticks": 2, "mttp_minutes": 35, "beta": "LOW"},
    "AAL":   {"zone_pct": 0.0020, "turn_ticks": 2, "mttp_minutes": 35, "beta": "LOW"},
    "INTC":  {"zone_pct": 0.0020, "turn_ticks": 2, "mttp_minutes": 35, "beta": "LOW"},
    "RIVN":  {"zone_pct": 0.0030, "turn_ticks": 3, "mttp_minutes": 35, "beta": "MID"},
    "HOOD":  {"zone_pct": 0.0030, "turn_ticks": 3, "mttp_minutes": 30, "beta": "MID"},
    "BAC":   {"zone_pct": 0.0020, "turn_ticks": 2, "mttp_minutes": 35, "beta": "LOW"},
    "SNAP":  {"zone_pct": 0.0030, "turn_ticks": 3, "mttp_minutes": 35, "beta": "MID"},
    "MARA":  {"zone_pct": 0.0040, "turn_ticks": 3, "mttp_minutes": 25, "beta": "HIGH"},
    "CCL":   {"zone_pct": 0.0025, "turn_ticks": 2, "mttp_minutes": 35, "beta": "LOW"},
    "UBER":  {"zone_pct": 0.0030, "turn_ticks": 3, "mttp_minutes": 30, "beta": "MID"},
    "NKE":   {"zone_pct": 0.0025, "turn_ticks": 2, "mttp_minutes": 35, "beta": "MID"},
}

def enrich_levels_with_beta(levels_data: dict) -> dict:
    """
    Enriches raw level dictionaries with beta, zone_pct, turn_ticks, and mttp_minutes:
    1. Filters out non-dictionary entries.
    2. Applies baseline rules from CONFIG_MAP.
    3. Respects explicit incoming JSON overrides.
    4. Auto-falls back to 'MID' tier defaults for unknown/test tickers.
    """
    enriched = {}
    is_standalone_test = list(levels_data.keys()) == ["test_ticker"]
    
    for ticker, val in levels_data.items():
        if (ticker == "test_ticker" and not is_standalone_test) or not isinstance(val, dict):
            continue
        
        cfg = CONFIG_MAP.get(ticker, {"zone_pct": 0.0030, "turn_ticks": 3, "mttp_minutes": 35, "beta": "MID"}).copy()
        ticker_payload = dict(val)
        
        # Merge baseline config with incoming ticker payload (explicit JSON overrides take precedence)
        merged = cfg
        merged.update(ticker_payload)
        enriched[ticker] = merged
    return enriched

def load_trading_levels(force_refresh: bool = False) -> dict:
    """Cloud-First Level Loader: S3 -> Local Disk -> In-Memory Cache with TTL."""
    global _CACHE
    now = time.time()
    if _CACHE["data"] and not force_refresh and (now - _CACHE["timestamp"] < CACHE_TTL):
        return _CACHE["data"]

    raw_data = None

    # 1. Attempt S3 Download
    try:
        s3 = boto3.client('s3', region_name=AWS_REGION)
        obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=S3_LEVELS_KEY)
        raw_data = json.loads(obj['Body'].read().decode('utf-8'))
    except Exception:
        pass

    # 2. Fallback to Local Disk
    if not raw_data and os.path.exists(LOCAL_LEVELS_PATH):
        try:
            with open(LOCAL_LEVELS_PATH, 'r') as f:
                raw_data = json.load(f)
        except Exception:
            pass

    if not raw_data:
        return {}

    valid_tickers = [k for k in raw_data.keys() if k != "test_ticker" or len(raw_data) == 1]
    if valid_tickers:
        _CACHE["data"] = enrich_levels_with_beta(raw_data)
        _CACHE["timestamp"] = now

    return _CACHE["data"]

def save_trading_levels(data: dict):
    """Atomic write-through update: saves locally, pushes to S3, and refreshes cache."""
    global _CACHE
    enriched_data = enrich_levels_with_beta(data) if data else {}
    _CACHE["data"] = enriched_data
    _CACHE["timestamp"] = time.time()

    # Atomic Write to Local Disk
    try:
        temp_path = f"{LOCAL_LEVELS_PATH}.tmp"
        with open(temp_path, 'w') as f:
            json.dump(enriched_data, f, indent=2)
        os.replace(temp_path, LOCAL_LEVELS_PATH)
    except Exception as e:
        print(f"[!] Error writing local levels file: {e}")

    # Sync to S3
    try:
        s3 = boto3.client('s3', region_name=AWS_REGION)
        s3.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=S3_LEVELS_KEY,
            Body=json.dumps(enriched_data, indent=2),
            ContentType="application/json"
        )
        print("[✓] Levels updated locally, cached in-memory, and synced to S3.")
    except Exception as e:
        print(f"[!] S3 Sync warning: {e}")

if __name__ == "__main__":
    data = load_trading_levels(force_refresh=True)
    print(f"[✓] Level Loader initialized. Loaded {len(data)} enriched tickers.")
