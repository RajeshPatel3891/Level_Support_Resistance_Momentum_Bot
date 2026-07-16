import os, requests
from dotenv import load_dotenv
load_dotenv()
url = f"https://sandbox.tradier.com/v1/accounts/{os.getenv('TRADIER_ACCOUNT_ID')}/orders"
headers = {"Authorization": f"Bearer {os.getenv('TRADIER_SANDBOX_TOKEN')}", "Accept": "application/json"}
print(requests.get(url, headers=headers).json())
