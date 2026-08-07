#!/bin/bash
echo "[*] Launching Harmonized Bot Streamer & Exit Monitor..."
python3 harmonized_bot_streamer.py &

echo "[*] Launching Harmonized Dashboard Server..."
exec python3 -m uvicorn dashboard_server:app --host 0.0.0.0 --port 8000
