import requests
import os

# You'll need your Tradier API token in your environment
token = os.getenv("TRADIER_API_TOKEN") 
response = requests.post(
    'https://api.tradier.com/v1/markets/events/session',
    headers={'Authorization': f'Bearer {token}'}
)

if response.status_code == 200:
    print(response.json()['stream']['sessionid'])
else:
    print("Error fetching session ID")
