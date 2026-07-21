#!/bin/bash
SESSION="harm_live_stack"

# Kill existing session completely
tmux kill-session -t $SESSION 2>/dev/null

# 0. LiveBot Execution Engine
tmux new-session -d -s $SESSION -n "LiveBot" "bash -c 'while true; do ./venv/bin/python src/LiveBot.py; echo \"[!] LiveBot exited. Restarting in 3s...\"; sleep 3; done; exec bash'"

# 1. GEX Exit Monitor
tmux new-window -t $SESSION -n "GEX_Monitor" "bash -c 'while true; do ./venv/bin/python3 src/gex_exit_monitor.py; echo \"[!] GEX Monitor exited. Restarting in 5s...\"; sleep 5; done; exec bash'"

# 2. Guardrails Audit Loop
tmux new-window -t $SESSION -n "Guardrails" "bash -c 'while true; do clear; ./venv/bin/python3 src/sync_market_data.py && ./venv/bin/python3 src/guardrail_audit.py; sleep 30; done; exec bash'"

# 3. MasterSentry
tmux new-window -t $SESSION -n "MasterSentry" "bash -c 'while true; do ./venv/bin/python3 src/MasterSentry.py; echo \"[!] MasterSentry exited. Restarting in 5s...\"; sleep 5; done; exec bash'"

# 4. Dashboard Data Generator
tmux new-window -t $SESSION -n "Dash_Gen" "bash -c 'while true; do ./venv/bin/python3 src/generate_dashboard_data.py; sleep 10; done; exec bash'"

# 5. Uvicorn Dashboard Server
tmux new-window -t $SESSION -n "Dash_Server" "bash -c './venv/bin/uvicorn dashboard_server:app --host 0.0.0.0 --port 8000 --reload; exec bash'"

# 6. DB Live Tail Monitor
tmux new-window -t $SESSION -n "DB_Tail" "bash -c 'while true; do clear; sqlite3 harm_telemetry.db \"SELECT timestamp, ticker, direction, spot_price, net_pnl, exit_status FROM trades ORDER BY timestamp DESC LIMIT 10;\"; sleep 5; done; exec bash'"

echo "[✓] harm_live_stack re-launched with 7 clean, active core windows!"
