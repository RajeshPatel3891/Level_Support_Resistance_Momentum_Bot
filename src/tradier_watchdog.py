import os, time, requests, json
from datetime import datetime
from pathlib import Path

TOKEN = os.getenv("TRADIER_TOKEN") or "CvtMHhNSylWy5KLTTvU29UD3zMdb"
BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1").rstrip("/")
ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "VA83416608")

def check_health():
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    start_time = time.time()
    try:
        res = requests.get(f"{BASE_URL}/accounts/{ACCOUNT_ID}/balances", headers=headers, timeout=5)
        latency = round((time.time() - start_time) * 1000, 2)
        
        status_data = {
            "timestamp": time.time(),
            "time_str": datetime.now().strftime("%H:%M:%S ET"),
            "status_code": res.status_code,
            "latency_ms": latency,
            "healthy": res.status_code == 200
        }
        
        Path("logs/heartbeats").mkdir(parents=True, exist_ok=True)
        with open("logs/heartbeats/TradierAPI.json", "w") as f:
            json.dump(status_data, f)
            
        if res.status_code != 200:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [🚨 TRADIER ALERT] API returned HTTP {res.status_code}: {res.text}")
        else:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [✓ TRADIER HEALTH] Latency: {latency}ms | Status: OK")
    except Exception as e:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [🔥 TRADIER DOWN] Connection exception: {e}")

if __name__ == "__main__":
    print("[⚙️] Tradier API Watchdog Initialized.")
    while True:
        check_health()
        time.sleep(60)
