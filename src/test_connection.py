import websocket
import os
import json
from datetime import datetime

def on_message(ws, message):
    print(f"Massive API Message: {message}")
    
    try:
        data = json.loads(message)
        for msg in data:
            if msg.get("ev") == "status" and msg.get("status") == "auth_success":
                print("--- Authentication Accepted! ---")
                print("Subscribing to IWM aggregate minute bars (Real-Time Test)...")
                sub_payload = json.dumps({"action": "subscribe", "params": "AM.IWM"})
                ws.send(sub_payload)
            
            # If we get market data, parse the timestamp to prove if it's delayed
            elif msg.get("ev") == "AM":
                end_time_ms = msg.get("e")
                if end_time_ms:
                    # Convert Unix milliseconds to human-readable format
                    readable_time = datetime.fromtimestamp(end_time_ms / 1000.0).strftime('%H:%M:%S')
                    print(f"\n---> DATA TIMESTAMP: {readable_time} (Compare this to your current clock!) <---\n")

    except Exception as e:
        pass

def on_error(ws, error):
    print(f"WebSocket Error: {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"Connection closed by server. Code: {close_status_code}")

def on_open(ws):
    print("Socket connected! Sending authentication payload...")
    api_key = os.getenv('MASSIVE_API_KEY')
    auth_payload = json.dumps({"action": "auth", "params": api_key})
    ws.send(auth_payload)

if __name__ == "__main__":
    api_key = os.getenv('MASSIVE_API_KEY')
    if not api_key:
        print("CRITICAL: MASSIVE_API_KEY is not in the environment.")
    else:
        # POINTED BACK TO REAL-TIME ENDPOINT
        ws_url = "wss://socket.massive.com/stocks"
        print(f"Connecting to {ws_url}...")
        
        ws = websocket.WebSocketApp(ws_url,
                                  on_open=on_open,
                                  on_message=on_message,
                                  on_error=on_error,
                                  on_close=on_close)
        
        ws.run_forever()
