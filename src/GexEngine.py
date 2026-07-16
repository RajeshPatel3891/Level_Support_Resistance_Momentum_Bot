# -*- coding: utf-8 -*-
import requests
import os
import time
from dotenv import load_dotenv

load_dotenv()

class GexEngine:
    def __init__(self, symbol="AAPL"):
        # Uses environment variable if present, otherwise falls back to the key provided
        self.api_key = os.getenv("FLASHALPHA_API_KEY", "xIf7d2EdumUoanjj1sBChqhM0zVa1xQJPiKoJbD3")
        self.base_url = "https://lab.flashalpha.com/v1"
        self.headers = {"X-Api-Key": self.api_key}
        self.symbol = symbol

    def get_exposure(self):
        """Fetches Gamma Flip, Call Wall, and Put Wall for the configured symbol."""
        try:
            url = f"{self.base_url}/exposure/levels/{self.symbol}"
            response = requests.get(url, headers=self.headers)
            
            # Check for Rate Limiting specifically
            if response.status_code == 429:
                print(f"[!] Rate limited. Sleeping for 5 minutes...")
                time.sleep(300)
                return None
                
            return response.json() if response.status_code == 200 else None
        except Exception as e:
            print(f"Error fetching GEX: {e}")
            return None

    def run(self):
        print(f"[*] GexEngine initializing for {self.symbol}...")
        while True:
            data = self.get_exposure()
            if data and 'levels' in data:
                # API structure: data['levels'] contains the metrics
                levels = data['levels']
                price = data.get('underlying_price', 'N/A')
                flip = levels.get('gamma_flip', 0)
                call_wall = levels.get('call_wall', 'N/A')
                put_wall = levels.get('put_wall', 'N/A')
                
                # Format flip safely
                flip_display = f"{flip:.2f}" if isinstance(flip, (int, float)) else flip
                
                print(f"[✓] {self.symbol} | Price: {price} | Flip: {flip_display} | Call Wall: {call_wall} | Put Wall: {put_wall}")
                
                # Polling interval increased to 5 minutes to stay within Free tier limits
                time.sleep(300)
            else:
                print("[!] Data unavailable or rate limited. Retrying in 60s...")
                time.sleep(60)

if __name__ == "__main__":
    engine = GexEngine(symbol="AAPL")
    engine.run()
