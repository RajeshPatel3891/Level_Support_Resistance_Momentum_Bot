import os, requests, json
token = os.getenv("TRADIER_SANDBOX_TOKEN")
account_id = os.getenv("TRADIER_ACCOUNT_ID")
headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
base_url = "https://sandbox.tradier.com/v1"

resp = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers).json()
positions = resp.get('positions', {}).get('position', [])

for pos in positions:
    print(json.dumps(pos, indent=2))
