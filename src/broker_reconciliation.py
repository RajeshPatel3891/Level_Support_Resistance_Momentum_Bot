import os
import time
import requests
import boto3
import uuid
import re
from datetime import datetime, timezone
import pytz

def reconcile_broker_state():
    """
    Bidirectional Broker Reconciliation:
    1. Detects live broker positions missing from DynamoDB and auto-adopts/registers them, placing an immediate stop.
    2. Detects DynamoDB active trades no longer present at the broker and safely closes them out.
    """
    token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN') or os.getenv('TRADIER_ACCESS_TOKEN')
    account_id = os.getenv('TRADIER_ACCOUNT_ID')
    base_url = os.getenv('TRADIER_BASE_URL', 'https://api.tradier.com/v1').rstrip('/')
    
    if not token or not account_id:
        return

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        res = requests.get(f"{base_url}/accounts/{account_id}/positions", headers=headers, timeout=5)
        if res.status_code != 200:
            return
         
        data = res.json()
        if not isinstance(data, dict):
            return

        positions_wrapper = data.get('positions', {})
        if not isinstance(positions_wrapper, dict):
            return

        position_list = positions_wrapper.get('position', [])
        if isinstance(position_list, dict):
            position_list = [position_list]
        elif not isinstance(position_list, list):
            position_list = []
         
        # Map OCC symbols to their position data dictionaries
        broker_positions = {p.get('symbol'): p for p in position_list if isinstance(p, dict) and p.get('symbol')}
        broker_symbols = set(broker_positions.keys())

        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        tenant_id = os.getenv('TENANT_ID', 'COMPANY_A_PROD')

        # Scan active trades in DynamoDB
        scan_res = table.scan(
            FilterExpression="tenant_id = :t AND exit_status = :s",
            ExpressionAttributeValues={":t": tenant_id, ":s": "ACTIVE"}
        )
        active_items = scan_res.get('Items', [])
        active_dynamo_symbols = {item.get('occ_symbol') or item.get('ticker') for item in active_items}

        # -------------------------------------------------------------
        # CASE 1: AUTO-ADOPT ORPHAN POSITIONS (Live at broker, missing in DynamoDB)
        # -------------------------------------------------------------
        orphan_symbols = broker_symbols - active_dynamo_symbols
        for occ in orphan_symbols:
            pos = broker_positions.get(occ, {})
            qty = float(pos.get('quantity', 1.0))
            total_cost = float(pos.get('cost_basis', 0.0))
            
            # Calculate per-contract unit entry price (Tradier returns total option cost basis = price * qty * 100)
            entry_price = round(total_cost / (qty * 100.0), 2) if total_cost > 0 else 0.35

            # Parse underlying root and option direction (CALL/PUT) from OCC string
            match = re.match(r'^([A-Z]+)\d{6}([CP])\d{8}$', occ)
            ticker = match.group(1) if match else "UNKNOWN"
            direction = "CALL" if match and match.group(2) == 'C' else "PUT"

            # Compute standard risk parameters (35% hard stop rule for options)
            if entry_price <= 1.00:
                stop_loss = round(max(0.10, entry_price * 0.65), 2)
            else:
                stop_loss = round(entry_price * 0.70, 2)
            take_profit = round(entry_price * 1.50, 2)

            trade_id = f"adopt_{str(uuid.uuid4())[:8]}"
            timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            print(f"[🛡️ AUTO-ADOPTION] Found untracked broker position: {qty}x {occ} (Entry: ${entry_price:.2f}). Registering in DynamoDB...")

            # Register in DynamoDB so Master Exit Monitor can pick it up
            item_payload = {
                'tenant_id': tenant_id,
                'trade_id': trade_id,
                'occ_symbol': occ,
                'ticker': ticker,
                'shares': str(int(qty)),
                'entry_price': str(entry_price),
                'stop_loss': str(stop_loss),
                'take_profit': str(take_profit),
                'exit_status': 'ACTIVE',
                'direction': direction,
                'timestamp': timestamp_str,
                'execution_env': os.getenv('EXECUTION_ENV', 'PROD'),
                'is_live': 1,
                'strategy': 'BROKER_AUTO_ADOPTED'
            }
            table.put_item(Item=item_payload)

            # Immediately post a protective stop order to Tradier
            stop_payload = {
                "class": "option",
                "symbol": ticker,
                "option_symbol": occ,
                "side": "sell_to_close",
                "quantity": str(int(qty)),
                "type": "stop",
                "stop": f"{stop_loss:.2f}",
                "duration": "day"
            }
            try:
                stop_res = requests.post(f"{base_url}/accounts/{account_id}/orders", data=stop_payload, headers=headers, timeout=5)
                if stop_res.status_code == 200:
                    print(f"[✓ ADOPTION SUCCESS] Protective stop placed @ ${stop_loss:.2f} for orphan position {occ}.")
            except Exception as stop_ex:
                print(f"[-] Failed to post protective stop for adopted position {occ}: {stop_ex}")

        # -------------------------------------------------------------
        # CASE 2: RECONCILE CLOSED POSITIONS (Active in DynamoDB, missing at broker)
        # -------------------------------------------------------------
        for item in active_items:
            occ = item.get('occ_symbol') or item.get('ticker')
            trade_id = item.get('trade_id')
            if occ and occ not in broker_symbols:
                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                table.update_item(
                    Key={'tenant_id': tenant_id, 'trade_id': trade_id},
                    UpdateExpression="SET exit_status = :closed, closed_at = :now",
                    ExpressionAttributeValues={":closed": "BROKER_RECONCILED_CLOSED", ":now": now_str}
                )
                print(f"[🧹 RECONCIER] Marked DynamoDB trade {trade_id} ({occ}) as CLOSED (missing from broker).")

    except Exception as e:
        print(f"[-] Broker Reconciler: DynamoDB sync error: {e}")
