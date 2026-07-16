import os, requests
from dotenv import load_dotenv
load_dotenv()
token = os.getenv("TRADIER_SANDBOX_TOKEN")
account_id = os.getenv("TRADIER_ACCOUNT_ID")
resp = requests.get(f"https://sandbox.tradier.com/v1/accounts/{account_id}/orders", 
                    headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'})
print(resp.json())
