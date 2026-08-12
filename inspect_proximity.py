import os
import requests
from dotenv import load_dotenv

load_dotenv()

TRADIER_TOKEN = os.getenv("TRADIER_TOKEN") or os.getenv("TRADIER_SANDBOX_TOKEN")
TRADIER_BASE_URL = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")

def inspect_proximity():
    print("==========================================================")
    print("🦅 HARM.AI // PROXIMITY INSPECTOR (TRADIER DEBUG)")
    print("==========================================================")
    if not TRADIER_TOKEN:
        print("[!] TRADIER_TOKEN not found in .env!")
        return

    url = f"{TRADIER_BASE_URL}/markets/quotes"
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    tickers = os.getenv("ACTIVE_TICKERS", "F,SOFI,AAL,RIVN")
    
    try:
        resp = requests.get(url, headers=headers, params={"symbols": tickers}, timeout=5)
        print(f"[DEBUG] Base URL: {TRADIER_BASE_URL}")
        print(f"[DEBUG] HTTP Status: {resp.status_code}")
        print(f"[DEBUG] Response Payload: {resp.text}")
        
        if resp.status_code == 200:
            data = resp.json()
            quotes_obj = data.get("quotes")
            if quotes_obj and quotes_obj != 'null':
                q_list = quotes_obj.get("quote", [])
                if isinstance(q_list, dict):
                    q_list = [q_list]
                for q in q_list:
                    print(f"[{q.get('symbol')}] Last: ${q.get('last')} | VWAP: ${q.get('vwap', 'N/A')}")
    except Exception as e:
        print(f"[!] Exception: {e}")

if __name__ == "__main__":
    inspect_proximity()
