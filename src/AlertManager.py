import requests

def send_discord_alert(ticker, action, price, reason):
    # Webhook URL for "Captain Hook"
    webhook_url = "https://discord.com/api/webhooks/1516048864325537847/fiH0REc5aHygxCfHFmplUA1tJlVfRJOI4MBRG4Oe0Kf_M2cigVyP5oPLgQvY9JG3vKk4"
    
    # Professional embed formatting
    color = 65280 if "BUY" in action else 16711680
    embed = {
        "title": f"Harmonized AI Trade Alert",
        "color": color,
        "fields": [
            {"name": "Asset", "value": ticker, "inline": True},
            {"name": "Action", "value": action, "inline": True},
            {"name": "Price", "value": f"${price:.2f}", "inline": True},
            {"name": "Reason", "value": reason, "inline": False}
        ]
    }
    
    try:
        requests.post(webhook_url, json={"embeds": [embed]})
    except Exception as e:
        print(f"Failed to send Discord alert: {e}")
