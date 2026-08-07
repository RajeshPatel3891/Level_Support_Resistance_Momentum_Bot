import requests
import json

def send_signal(signal_data, webhook_url):
    """
    Sends the structured JSON signal to a notification endpoint.
    """
    message = {
        "content": f"🚨 **STRATEGY SIGNAL: {signal_data['action']}** 🚨",
        "embeds": [{
            "title": f"Ticker: {signal_data['ticker']}",
            "description": signal_data['reason'],
            "color": 65280 if "BUY" in signal_data['action'] else 16711680
        }]
    }
    
    response = requests.post(webhook_url, json=message)
    return response.status_code
