import requests
import os
from dotenv import load_dotenv

class GexGateway:
    def __init__(self):
        load_dotenv(dotenv_path=os.path.join(os.getcwd(), '.env'))
        self.api_key = os.getenv("FLASH_ALPHA_KEY")
        self.base_url = "https://lab.flashalpha.com/v1"
        self.headers = {'X-Api-Key': self.api_key}

    def get_gex_levels(self, symbol, expiration="2026-07-17"): # Defaulting to this Friday
        url = f"{self.base_url}/exposure/gex/{symbol}"
        params = {'expiration': expiration}
        try:
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"[!] FlashAlpha Error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            print(f"[!] GexGateway Connection Error: {e}")
            return None
