import os, requests
from dotenv import load_dotenv
load_dotenv()
token = os.getenv("TRADIER_SANDBOX_TOKEN")
account_id = os.getenv("TRADIER_ACCOUNT_ID")
base_url = "https://sandbox.tradier.com/v1"
headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

# Get all orders
orders = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers).json()
for o in orders.get('orders', {}).get('order', []):
    if o['status'] in ['pending', 'open']:
        print(f"Canceling order {o['id']} ({o['symbol']})...")
        requests.delete(f"{base_url}/accounts/{account_id}/orders/{o['id']}", headers=headers)
