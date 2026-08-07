import os, sys, json, websocket, time, ssl

def connect_massive_stream(on_message_callback):
    api_key = os.environ.get("MASSIVE_API_KEY")
    # Using the standard delayed endpoint
    url = "wss://delayed.massive.com/stocks"
    
    while True:
        try:
            print(f"Sentry: Connecting to {url}...", file=sys.stderr)
            ws = websocket.WebSocketApp(
                url,
                on_message=on_message_callback,
                # Some gateways require the key in the header, not the body
                header={"Authorization": f"Bearer {api_key}"},
                on_open=lambda ws: ws.send(json.dumps({"action": "subscribe", "params": "T.IWM"})),
                on_error=lambda ws, err: print(f"Sentry: WS Error: {err}", file=sys.stderr),
                on_close=lambda ws, code, msg: print(f"Sentry: Connection closed: {code} - {msg}", file=sys.stderr)
            )
            ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}, ping_interval=20, ping_timeout=10)
            time.sleep(5) 
        except Exception as e:
            print(f"Sentry: CRASHED: {e}. Retrying...", file=sys.stderr)
            time.sleep(5)
