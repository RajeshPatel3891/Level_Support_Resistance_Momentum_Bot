import os, requests

token = os.environ.get("TRADIER_TOKEN")
acct = os.environ.get("TRADIER_ACCOUNT_ID", "6YB87601")
headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}

res = requests.get(f"https://api.tradier.com/v1/accounts/{acct}/positions", headers=headers)
positions = res.json().get("positions", {}).get("position", [])
if isinstance(positions, dict):
    positions = [positions]

print("--- TRADIER LIVE POSITIONS ---")
for p in positions:
    sym = p.get("symbol")
    qty = p.get("quantity")
    cost = p.get("cost_basis")
    print(f"{sym}: {qty}x @ Cost ${cost}")
