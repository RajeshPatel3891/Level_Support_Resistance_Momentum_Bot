import os
import sys
import sqlite3
import json
from datetime import datetime
import src.LiveBot as LiveBot
from unittest.mock import patch, MagicMock

sys.path.append(os.getcwd())

def run_limit_order_test():
    print("[*] Preparing Test Database state...")
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trades WHERE ticker = 'PLTR'")
    # Added strategy, direction, and is_live to satisfy schema constraints
    cursor.execute("""
        INSERT INTO trades (ticker, timestamp, strategy, direction, spot_price, stop_loss, take_profit, exit_status, is_live) 
        VALUES ('PLTR', ?, 'BREAKOUT', 'CALL', 131.00, 129.50, 135.00, 'ACTIVE', 1)
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
    conn.commit()
    conn.close()

    LiveBot.sync_active_trades_from_db()
    
    print("[*] Simulating Price Breach at $136.00 (Above Take Profit of $135.00)...")
    
    with patch('requests.post') as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"order": {"id": "TEST_123"}}
        mock_post.return_value = mock_response

        LiveBot.check_active_trade_exits("PLTR", 136.00)

        if mock_post.called:
            args, kwargs = mock_post.call_args
            payload = kwargs.get('data')
            
            print("\n[✓] EXIT DISPATCHED SUCCESSFULLY!")
            print(f"[*] Payload Inspection:")
            print(f"    - Type: {payload.get('type')}")
            print(f"    - Limit Price: {payload.get('price')}")
            
            assert payload.get('type') == 'limit', "❌ FAIL: Order type is not 'limit'!"
            assert payload.get('price') == '135.0', "❌ FAIL: Limit price does not match target!"
            print("[✓] PASS: Limit order logic verified.")
        else:
            print("❌ FAIL: No order was dispatched!")

if __name__ == "__main__":
    run_limit_order_test()
