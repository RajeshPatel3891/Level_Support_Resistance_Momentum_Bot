import os
import sys
import json
import asyncio
import websockets

def load_trading_levels():
    try:
        with open('trading_levels.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("CRITICAL: trading_levels.json not found!")
        sys.exit(1)

TRADING_LEVELS = load_trading_levels()
WATCHLIST_SYMBOLS = list(TRADING_LEVELS.keys())

async def market_stream_listener():
    # Retrieve the API key injected via your Docker runtime environment
    api_key = os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        print("CRITICAL: MASSIVE_API_KEY environment variable is missing!")
        sys.exit(1)
        
    uri = "wss://stream.massive.com/v1/stocks"
    
    print("Harmonized AI Sentry v1.8.0 Online. [Mode: MASSIVE_LIVE_STREAM]")
    print(f"Targeting Watchlist: {WATCHLIST_SYMBOLS}")

    async with websockets.connect(uri) as websocket:
        # 1. Authenticate with Massive's Server per documentation
        auth_message = {
            "action": "auth",
            "key": api_key
        }
        await websocket.send(json.dumps(auth_message))
        print("Sent authentication payload...")
        
        # 2. Subscribe to trade execution prints for your watchlist
        subscribe_message = {
            "action": "subscribe",
            "trades": WATCHLIST_SYMBOLS
        }
        await websocket.send(json.dumps(subscribe_message))
        print(f"Sent subscription request for {WATCHLIST_SYMBOLS}")
        
        # 3. Process the incoming stream arrays
        async for message in websocket:
            events = json.loads(message)
            
            # Massive streams data as an array of objects
            for event in events:
                if event.get("ev") == "T":  # 'T' stands for Trade execution
                    symbol = event.get("sym")  # Ticker symbol
                    price = event.get("p")     # Execution price
                    volume = event.get("v")    # Size of the trade execution
                    
                    # Pull baseline metrics from your json manifest
                    symbol_config = TRADING_LEVELS.get(symbol, {})
                    avg_volume = symbol_config.get("avg_volume", 1000)
                    
                    # Core Volume-Validation Sentry Logic (1.9x threshold)
                    if volume > (avg_volume * 1.9):
                        print(f"\n[LIVE STREAM SPIKE] {symbol} @ ${price:.2f} | Size: {volume} (1.9x Spike!)")
                        # Fire your high-conviction Discord alert hooks here

if __name__ == "__main__":
    try:
        asyncio.run(market_stream_listener())
    except KeyboardInterrupt:
        print("\nSentry stream gracefully paused by user.")
        sys.exit(0)
