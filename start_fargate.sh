#!/bin/bash
echo "=========================================================="
echo "🚀 LAUNCHING HARMONIZED 8-SERVICE TRADING SUITE"
echo "=========================================================="

echo "[1/8] Initializing & Migrating SQLite Database Schemas..."
python3 rebuild_db.py
python3 preboot_db_fix.py

echo "[2/8] Running System Preflight Integrity Guard..."
python3 preflight_guard.py

echo "[3/8] Launching Harmonized Bot Streamer..."
python3 -u harmonized_bot_streamer.py &

echo "[4/8] Launching Production Gateway (Port 8000)..."
python3 -u production_gateway.py &

echo "[5/8] Launching Telemetry Bridge..."
python3 -u telemetry_bridge.py &

echo "[6/8] Launching Proximity DB Engine..."
python3 -u proximity_db.py &

echo "[7/8] Launching Continuous GEX & MTTP Exit Daemon..."
python3 -u run_gex_monitor.py &

echo "[8/8] Launching Harmonized Dashboard Server (Port 8080)..."
exec python3 -u -m uvicorn dashboard_server:app --host 0.0.0.0 --port 8080
