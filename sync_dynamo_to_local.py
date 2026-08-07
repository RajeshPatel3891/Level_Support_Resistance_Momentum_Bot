import boto3
import sqlite3
import json

# 1. Connect to DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('HarmonizedTrades')

key_attrs = [k['AttributeName'] for k in table.key_schema]

response = table.scan()
items = response.get('Items', [])

# 2. Connect to local SQLite
conn = sqlite3.connect('harm_telemetry.db')
cursor = conn.cursor()

total_realized = 0.0
closed_list = []

for item in items:
    trade_id = str(item.get('trade_id', ''))
    ticker = str(item.get('ticker', ''))
    direction = str(item.get('direction', 'CALL'))
    entry = float(item.get('entry_price', 0.0) or 0.0)
    exit_px = float(item.get('exit_price', 0.0) or 0.0)
    sl = float(item.get('stop_loss', 0.0) or 0.0)
    tp = float(item.get('take_profit', 0.0) or 0.0)
    status = str(item.get('exit_status', 'ACTIVE'))
    shares = int(float(item.get('shares', 1) or 1))
    ts = str(item.get('exit_timestamp', item.get('timestamp', '')))
    
    pnl = round((exit_px - entry) * shares * 100, 2) if exit_px > 0 else 0.0
    reason = str(item.get('cso_reason') or item.get('cso_notes') or status)

    if status != 'ACTIVE':
        total_realized += pnl

    # Formatted strings matching Jinja template fields
    pnl_str = f"${pnl:+.2f}"
    pnl_class = "text-red-400" if pnl < 0 else "text-emerald-400"
    sl_str = f"${sl:.2f}" if sl else "N/A"
    tp_str = f"${tp:.2f}" if tp else "N/A"
    entry_str = f"${entry:.2f}"
    exit_str = f"${exit_px:.2f}"

    # Update local SQLite
    cursor.execute("""
        UPDATE trades 
        SET entry_price = ?,
            exit_price = ?,
            stop_loss = ?,
            take_profit = ?,
            exit_status = ?,
            net_pnl = ?,
            cso_notes = ?
        WHERE ticker = ? AND direction = ? AND (timestamp = ? OR id = ?)
    """, (entry, exit_px, sl, tp, status, pnl, reason, ticker, direction, ts, trade_id))

    closed_list.append({
        "id": trade_id,
        "ticker": ticker,
        "direction": direction,
        "strategy": item.get("strategy", "SMART_CSO_LIVE"),
        "entry_price": entry_str,
        "exit_price": exit_str,
        "stop_loss": sl_str,
        "take_profit": tp_str,
        "target": tp_str,
        "cso_notes": reason,
        "cso_reason": reason,
        "status": status,
        "exit_status": status,
        "timestamp": ts,
        "dollar_pnl": pnl_str,
        "realized_pnl": pnl,
        "pnl_class": pnl_class,
        "contracts": str(shares)
    })

conn.commit()
conn.close()

# Save compiled JSON dataset locally
data = {
    "active_trades": [],
    "closed_trades": closed_list,
    "total_realized_closed": round(total_realized, 2)
}

with open("dashboard_data.json", "w") as f:
    json.dump(data, f, indent=2)

print(f"[✓] Synced with exact Jinja template keys!")
print(f"[✓] Total Realized PnL: ${total_realized:+.2f}")
