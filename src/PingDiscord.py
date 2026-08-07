import requests
import sys

webhook_url = "https://discord.com/api/webhooks/1516048864325537847/fiH0REc5aHygxCfHFmplUA1tJlVfRJOI4MBRG4Oe0Kf_M2cigVyP5oPLgQvY9JG3vKk4"
payload = {"content": "Sentry Test: Connection established."}

try:
    response = requests.post(webhook_url, json=payload)
    print(f"DEBUG: Response Code: {response.status_code}")
    print(f"DEBUG: Response Text: {response.text}")
except Exception as e:
    print(f"DEBUG: Error: {e}")
