import os
import json
import time
import boto3

_CACHE = {"timestamp": 0, "data": {}}
CACHE_TTL = 7200  # Fallback 2-hour TTL

def load_trading_levels(force_refresh=False):
    global _CACHE
    now = time.time()
    
    # If forced, or cache is empty, or TTL expired
    if force_refresh or not _CACHE["data"] or (now - _CACHE["timestamp"] > CACHE_TTL):
        bucket_name = os.getenv("S3_BUCKET_NAME", "harmonized-ai-telemetry-bucket")
        local_path = "trading_levels.json"
        
        # Only pull from S3 if local doesn't exist or explicit sync is requested
        if not os.path.exists(local_path):
            try:
                s3 = boto3.client("s3", region_name="us-east-1")
                s3.download_file(bucket_name, "config/trading_levels.json", local_path)
            except Exception:
                pass

        try:
            with open(local_path, "r") as f:
                data = json.load(f)
                _CACHE["data"] = data
                _CACHE["timestamp"] = now
        except Exception as e:
            print(f"[!] Error loading trading levels: {e}")
            
    return _CACHE["data"]

def save_trading_levels(data):
    """Write-through update: saves locally, pushes to S3, and immediately invalidates cache."""
    global _CACHE
    local_path = "trading_levels.json"
    
    with open(local_path, "w") as f:
        json.dump(data, f, indent=2)
        
    # Immediately update memory cache so sync_market_data sees changes instantly
    _CACHE["data"] = data
    _CACHE["timestamp"] = time.time()
        
    bucket_name = os.getenv("S3_BUCKET_NAME", "harmonized-ai-telemetry-bucket")
    try:
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.upload_file(local_path, bucket_name, "config/trading_levels.json")
        print("[✓] Levels updated locally, cached in-memory, and synced to S3.")
    except Exception as e:
        print(f"[!] S3 Sync failed: {e}")
