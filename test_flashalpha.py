from src.GexGateway import GexGateway

gateway = GexGateway()
# Ensure this date is a valid expiration for MSFT
data = gateway.get_gex_levels("MSFT", expiration="2026-07-17")

if data:
    print(f"Data Received for MSFT (2026-07-17):")
    print(f"- Gamma Flip: {data.get('gamma_flip')}")
    print(f"- Call Wall: {data.get('call_wall')}")
else:
    print("Failed to retrieve data.")
