import os
import sys
import time
import json
import sqlite3
import requests

def test_telemetry_freshness():
    print("==========================================================")
    print("🧪 HARMONIZED AI // TELEMETRY & PROCESS HEALTH INTEGRITY")
    print("==========================================================")
    
    failures = []
    
    # --- TEST 1: Check File Modification Age ---
    json_path = "trading_levels.json"
    if os.path.exists(json_path):
        mtime = os.path.getmtime(json_path)
        age_seconds = time.time() - mtime
        print(f"[*] trading_levels.json last modified: {age_seconds:.1f}s ago")
        if age_seconds > 30:
            failures.append(f"STALE JSON: trading_levels.json hasn't been updated in {age_seconds:.1f}s")
    else:
        failures.append("MISSING FILE: trading_levels.json does not exist locally")

    # --- TEST 2: Sample API Delta Over 5 Seconds ---
    url = "http://localhost:8000/api/proximity"
    try:
        r1 = requests.get(url, timeout=3).json()
        time.sleep(5)
        r2 = requests.get(url, timeout=3).json()
        
        if r1 == r2:
            failures.append("API FROZEN: /api/proximity returned 100% identical data 5 seconds apart")
        else:
            print("[✓] API proximity data is actively changing over time.")
    except Exception as e:
        failures.append(f"API ERROR: Could not reach {url} -> {e}")

    # --- TEST 3: Spot vs VWAP Static Equality Check ---
    if os.path.exists(json_path):
        with open(json_path) as f:
            data = json.load(f)
        
        static_count = 0
        total_count = len(data)
        for ticker, metrics in data.items():
            spot = metrics.get('spot', 0)
            vwap = metrics.get('vwap', 0)
            if spot > 0 and spot == vwap:
                static_count += 1
        
        if total_count > 0 and static_count == total_count:
            failures.append(f"STATIC VWAP: 100% of tickers ({static_count}/{total_count}) have Spot == VWAP exactly.")

    # --- FINAL VERDICT ---
    print("\n----------------------------------------------------------")
    if failures:
        print("🚨 VERDICT: FALSE POSITIVE DETECTED!")
        for fail in failures:
            print(f"   ❌ {fail}")
        sys.exit(1)
    else:
        print("✅ VERDICT: LIVE STREAM ACTIVE & VALIDATED!")
        sys.exit(0)

if __name__ == "__main__":
    test_telemetry_freshness()
