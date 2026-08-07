import os
import requests

# Simple .env loader
if os.path.exists(".env"):
    with open(".env", "r") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ[k] = v.strip('"').strip("'")

token = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
account_id = os.getenv("TRADIER_ACCOUNT_ID")
base_url = os.getenv("TRADIER_BASE_URL", "https://sandbox.tradier.com/v1")

headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
resp = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers)

if resp.status_code == 200:
    data = resp.json()
    orders_wrapper = data.get("orders")
    if orders_wrapper and orders_wrapper != "null":
        orders = orders_wrapper.get("order", [])
        if isinstance(orders, dict):
            orders = [orders]
        for o in orders:
            status = o.get("status")
            if status in ["rejected", "canceled", "error"]:
                print(f"ID: {o.get('id')} | Symbol: {o.get('symbol')} | Status: {status} | Reason: {o.get('reason')}")
    else:
        print("[-] No orders found in account history.")
else:
    print(f"[-] API Error: {resp.status_code} - {resp.text}")
