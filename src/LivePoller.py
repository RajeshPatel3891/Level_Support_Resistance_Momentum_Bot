import requests, time, json, os, tempfile
from dotenv import load_dotenv
load_dotenv()

TICKERS = ["IWM", "QQQ", "GOOGL", "AMZN", "AAPL", "NVDA", "TSLA"]
API_KEY = os.environ.get('MASSIVE_API_KEY')
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

def poll_market():
    all_signals = []
    for symbol in TICKERS:
        try:
            url = f"https://api.massive.com/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}"
            response = requests.get(url, headers=HEADERS, timeout=5)
            if response.status_code == 200:
                data = response.json()
                ticker_data = data.get("ticker", {})
                trade_event = {
                    "id": f"{symbol}_{int(time.time())}",
                    "ticker": symbol,
                    "price": ticker_data.get("lastTrade", {}).get("p"),
                    "volume": ticker_data.get("lastTrade", {}).get("s"),
                    "status": "PENDING_BACKTEST",
                    "timestamp": time.time()
                }
                all_signals.append(trade_event)
                print(f"[POLLER] Updated {symbol}: {trade_event['price']}")
        except Exception as e:
            print(f"[POLLER] Error polling {symbol}: {e}")

    # Atomic write of the full signal list
    if all_signals:
        with tempfile.NamedTemporaryFile('w', dir='.', delete=False) as tf:
            json.dump(all_signals, tf)
            temp_name = tf.name
        os.replace(temp_name, "active_signals.json")

if __name__ == "__main__":
    while True:
        poll_market()
        time.sleep(5)
