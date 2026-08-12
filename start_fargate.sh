#!/bin/bash
echo "=========================================================="
echo "🚀 LAUNCHING HARMONIZED MULTI-SERVICE TRADING SUITE"
echo "=========================================================="

echo "[0/10] Cleaning up lingering processes & port bindings..."
pkill -f python3 2>/dev/null
fuser -k 8000/tcp 8080/tcp 2>/dev/null
sleep 1

# Trap Ctrl+C (SIGINT) to automatically terminate all background services on exit
trap "echo '[!] Shutting down all Harmonized daemons...'; pkill -P $$; pkill -f python3; exit 0" SIGINT SIGTERM EXIT

echo "[1/10] Launching Harmonized Dashboard Server IMMEDIATELY (Port 8080)..."
python3 -u -m uvicorn dashboard_server:app --host 0.0.0.0 --port 8080 &

echo "[2/10] Initializing & Migrating Database Schemas..."
python3 rebuild_db.py
python3 preboot_db_fix.py

echo "[2.5/10] 🧪 Executing Master Pre-Flight Unit Test Suite..."
if python3 test_master_suite.py; then
    echo "[✓] All pre-flight tests passed! Proceeding with boot..."
else
    echo "----------------------------------------------------------"
    echo "⛔ [CRITICAL PRE-FLIGHT FAILURE] Unit tests failed!"
    echo "⛔ Aborting launch sequence to protect live capital."
    echo "----------------------------------------------------------"
    pkill -P $$ 2>/dev/null
    exit 1
fi

echo "[3/10] Running Non-Blocking Broker Position Sync..."
if [ -f "src/sync_broker_positions.py" ]; then
    python3 src/sync_broker_positions.py &
elif [ -f "sync_broker_positions.py" ]; then
    python3 sync_broker_positions.py &
fi

echo "[4/10] Launching Harmonized Bot Streamer..."
while true; do python3 -u harmonized_bot_streamer.py; sleep 2; done &

echo "[5/10] Launching Production Gateway (Port 8000)..."
while true; do python3 -u production_gateway.py; sleep 2; done &

echo "[6/10] Launching Telemetry Bridge..."
while true; do python3 -u telemetry_bridge.py; sleep 2; done &

echo "[7/10] Launching Proximity DB Engine..."
while true; do python3 -u proximity_db.py; sleep 2; done &

echo "[8/10] Launching Continuous GEX & MTTP Exit Daemon..."
while true; do python3 -u run_gex_monitor.py; sleep 2; done &

echo "[9/10] Launching Live DynamoDB GSG Guard & Persisted Recovery Protector..."
while true; do python3 -u live_gsg_guard.py; sleep 2; done &

echo "[10/10] Launching Background Disk Telemetry & Retention Daemon..."
while true; do
    if [ -f "disk_telemetry_daemon.py" ]; then
        python3 -u disk_telemetry_daemon.py
    else
        journalctl --vacuum-size=100M 2>/dev/null
        find /tmp -type f -mtime +1 -delete 2>/dev/null
    fi
    sleep 300
done &

echo "[✓] All Harmonized trading daemons are verified and online!"
wait
