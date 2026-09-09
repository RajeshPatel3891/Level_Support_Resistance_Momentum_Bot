import os
import time
import requests
import boto3
import uuid
import re
from datetime import datetime, timezone
from dotenv import load_dotenv

if os.path.exists('.env.prod'):
    load_dotenv('.env.prod', override=True)
else:
    load_dotenv(override=True)

def get_tenant_id():
    explicit = os.getenv('TENANT_ID')
    if explicit:
        return explicit
    exec_env = os.getenv('EXECUTION_ENV', 'SANDBOX').upper()
    if exec_env in ['PROD', 'PRODUCTION', 'LIVE']:
        return 'COMPANY_A_PROD'
    return 'COMPANY_A_SANDBOX'

# Track consecutive poll misses before closing: {occ_symbol: miss_count}
MISSING_BROKER_POLL_COUNTS = {}

def has_active_broker_stop(occ_symbol, account_id, base_url, headers):
    try:
        url = f"{base_url}/accounts/{account_id}/orders"
        res = requests.get(url, headers=headers, timeout=4)
        if res.status_code == 200:
            orders_data = res.json().get('orders', {}).get('order', [])
            if isinstance(orders_data, dict):
                orders_data = [orders_data]
            for od in orders_data:
                if (od.get('option_symbol') == occ_symbol 
                    and od.get('status') in ['open', 'pending'] 
                    and od.get('side') == 'sell_to_close'):
                    return True
    except Exception:
        pass
    return False

def reconcile_broker_state():
    """
    True Bidirectional Broker Reconciliation:
    1. Broker is Ground Truth: If the broker holds contracts, DynamoDB MUST be ACTIVE.
       - If a record exists (even if marked CLOSED), resurrect it to ACTIVE.
       - If no record exists, adopt it as a new trade AND post protective stop.
    2. Debounced Closure: Only mark DynamoDB CLOSED if the position is missing
       from the broker across 3 consecutive cycles (prevents race conditions during fills).
    """
    token = os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_PROD_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN')
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
          
        broker_positions = {}
        for p in position_list:
            if isinstance(p, dict) and p.get('symbol'):
                qty = float(p.get('quantity') or 0.0)
                if qty > 0:
                    broker_positions[p.get('symbol')] = p

        broker_symbols = set(broker_positions.keys())

        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        tenant_id = get_tenant_id()

        # Scan ALL records for this tenant to check both ACTIVE and accidentally CLOSED
        scan_res = table.scan(
            FilterExpression="tenant_id = :t",
            ExpressionAttributeValues={":t": tenant_id}
        )
        all_tenant_items = scan_res.get('Items', [])

        active_items = [it for it in all_tenant_items if it.get('exit_status') == 'ACTIVE']

        # -------------------------------------------------------------
        # DIRECTION B (BROKER -> DYNAMO): Enforce Broker Ground Truth
        # -------------------------------------------------------------
        for occ, pos in broker_positions.items():
            qty = float(pos.get('quantity', 1.0))
            cost_basis = float(pos.get('cost_basis', 0.0))
            entry_px = round(cost_basis / (qty * 100.0), 2) if (qty > 0 and cost_basis > 0) else 0.35

            # Check if this contract exists in DynamoDB in ANY status
            matching_items = [it for it in all_tenant_items if (it.get('occ_symbol') == occ or it.get('ticker') == occ)]

            match = re.match(r'^([A-Z]+)\d{6}([CP])\d{8}$', occ)
            ticker = match.group(1) if match else occ
            direction = "CALL" if match and match.group(2) == 'C' else "PUT"

            if entry_px <= 1.00:
                stop_loss = round(max(0.10, entry_px * 0.65), 2)
            else:
                stop_loss = round(entry_px * 0.70, 2)
            take_profit = round(entry_px * 1.50, 2)

            if matching_items:
                target = matching_items[-1]
                t_id = target.get('trade_id')
                current_status = target.get('exit_status')

                if current_status != 'ACTIVE':
                    print(f"🚨 [GHOST RECOVERY] Broker holds {qty}x {occ} but DynamoDB marked {current_status}. Resurrecting trade_id {t_id} to ACTIVE!")
                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': t_id},
                        UpdateExpression="SET exit_status = :act, shares = :sh, cso_notes = :note",
                        ExpressionAttributeValues={
                            ":act": "ACTIVE",
                            ":sh": str(int(qty)),
                            ":note": "RESURRECTED_FROM_BROKER_TRUTH"
                        }
                    )
            else:
                # Completely untracked broker position: Adopt & register
                trade_id = f"adopt_{str(uuid.uuid4())[:8]}"
                timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

                print(f"[🛡️ AUTO-ADOPTION] Found untracked broker position: {qty}x {occ} (Entry: ${entry_px:.2f}). Registering in DynamoDB...")
                item_payload = {
                    'tenant_id': tenant_id,
                    'trade_id': trade_id,
                    'occ_symbol': occ,
                    'ticker': ticker,
                    'shares': str(int(qty)),
                    'entry_price': str(entry_px),
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

            # Ensure resting broker stop is active
            if not has_active_broker_stop(occ, account_id, base_url, headers):
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
                        print(f"[✓ ADOPTION SUCCESS] Protective stop placed @ ${stop_loss:.2f} for {occ}.")
                except Exception as stop_ex:
                    print(f"[-] Failed to post protective stop for {occ}: {stop_ex}")

        # -------------------------------------------------------------
        # DIRECTION A (DYNAMO -> BROKER): Debounced Clean-Up
        # -------------------------------------------------------------
        for item in active_items:
            occ = item.get('occ_symbol') or item.get('ticker')
            trade_id = item.get('trade_id')

            if occ and occ not in broker_symbols:
                misses = MISSING_BROKER_POLL_COUNTS.get(occ, 0) + 1
                MISSING_BROKER_POLL_COUNTS[occ] = misses

                if misses >= 3:
                    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': trade_id},
                        UpdateExpression="SET exit_status = :closed, closed_at = :now, cso_notes = :cn",
                        ExpressionAttributeValues={
                            ":closed": "BROKER_RECONCILED_CLOSED",
                            ":now": now_str,
                            ":cn": "CONFIRMED_ZERO_BROKER_QTY_3_CYCLES"
                        }
                    )
                    print(f"[🧹 RECONCILER] Verified 3 consecutive empty cycles. Marked {trade_id} ({occ}) as CLOSED.")
                    MISSING_BROKER_POLL_COUNTS.pop(occ, None)
                else:
                    print(f"[⏳ RECONCILER GRACE] {occ} missing at broker ({misses}/3 cycles). Holding status...")
            else:
                MISSING_BROKER_POLL_COUNTS.pop(occ, None)

    except Exception as e:
        print(f"[-] Broker Reconciler Error: {e}")

if __name__ == "__main__":
    reconcile_broker_state()
