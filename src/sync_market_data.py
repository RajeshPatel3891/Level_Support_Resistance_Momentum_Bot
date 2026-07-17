import json, requests

# Minimal dictionary of current prices (Replace with an API call if desired)
# Current NVDA is ~$206.85
LIVE_PRICES = {
    "NVDA": 206.85, "INTC": 98.40, "TSLA": 390.0, 
    "AAPL": 328.0, "PLTR": 133.0, "RIVN": 17.15,
    "SOFI": 17.15, "F": 14.15, "AAL": 15.60
}

def sync():
    with open("trading_levels.json", "r") as f:
        data = json.load(f)

    for ticker, price in LIVE_PRICES.items():
        if ticker in data:
            data[ticker]["last_price"] = price

    with open("trading_levels.json", "w") as f:
        json.dump(data, f, indent=2)
    print("[✓] Market prices synced to trading_levels.json")

if __name__ == "__main__":
    sync()
