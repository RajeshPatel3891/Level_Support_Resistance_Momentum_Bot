from src.AlertManager import send_discord_alert

print("Sending test alert to Discord...")
send_discord_alert(
    ticker="TEST-ASSET", 
    action="BUY", 
    price=123.45, 
    reason="This is a connectivity test for the Harmonized AI platform."
)
print("Test complete. Check your Discord 'Trading Bot Alerts' server.")
