#!/usr/bin/env python3
"""
HARM.AI // TRADIER AUTHORITATIVE BROKER RECONCILIATION ENGINE
===============================================================================
Source of Truth: Tradier API (GET /accounts/{id}/positions).
Action:
1. Purge: If DynamoDB or SQLite has ACTIVE trades not in Tradier -> Mark CLOSED.
2. Adopt: If Tradier has a position not marked ACTIVE in DB -> Insert/Adopt.
"""

import os
import sys
import time
import json
import sqlite3
import requests
import boto3
import re
from datetime import datetime as dt
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "harm_telemetry.db")

# Preload production environment if present
if os.path.exists(os.path.join(BASE_DIR, '.env.prod')):
    load_dotenv(os.path.join(BASE_DIR, '.env.prod'), override=True)
else:
    load_dotenv(override=True)

def get_auth_context():
    exec_env = os.getenv('EXECUTION_ENV', 'SANDBOX').upper()
    is_prod = exec_env in ['PROD', 'PRODUCTION', 'LIVE']
    
    if is_prod and os.path.exists(os.path.join(BASE_DIR, '.env.prod')):
        load_dotenv(os.path.join(BASE_DIR, '.env.prod'), override=True)
    elif os.path.exists(os.path.join(BASE_DIR, '.env.sandbox')):
        load_dotenv(os.path.join(BASE_DIR, '.env.sandbox'), override=True)
    else:
        load_dotenv(override=True)

    token = os.getenv('TRADIER_PROD_TOKEN' if is_prod else 'TRADIER_SANDBOX_TOKEN') or os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_ACCESS_TOKEN')
    account_id = os.getenv('TRADIER_ACCOUNT_ID')
    base_url = "https://api.tradier.com/v1" if is_prod else "https://sandbox.tradier.com/v1"
    tenant_id = os.getenv('TENANT_ID', 'COMPANY_A_PROD' if is_prod else 'COMPANY_A')

    return token, account_id, base_url, tenant_id

def reconcile_broker_state():
    token, account_id, base_url, tenant_id = get_auth_context()
    if not token or not account_id:
        return {}

    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    url = f"{base_url}/accounts/{account_id}/positions"

    # 1. Fetch Ground Truth from Tradier
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            print(f"[-] Broker Reconciler: Tradier API responded {res.status_code}. Aborting cycle.")
            return {}
        data = res.json()
    except Exception as e:
        print(f"[-] Broker Reconciler: Connection error: {e}")
        return {}

    positions_data = data.get('positions', {})
    if not isinstance(positions_data, dict):
        positions_data = {}
    raw_positions = positions_data.get('position', [])
    if isinstance(raw_positions, dict):
        raw_positions = [raw_positions]

    # Map of actual live holdings: {occ_symbol: position_dict}
    broker_positions = {}
    for p in raw_positions:
        sym = p.get('symbol')
        qty = float(p.get('quantity', 0))
        if sym and qty > 0:
            broker_positions[sym] = p

    # 2. Reconcile Remote DynamoDB
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        res = table.scan(FilterExpression=Attr('tenant_id').eq(tenant_id) & Attr('exit_status').eq('ACTIVE'))
        dynamo_active = res.get('Items', [])

        with table.batch_writer() as batch:
            for item in dynamo_active:
                occ = item.get('occ_symbol', item.get('ticker'))
                if occ not in broker_positions:
                    # Phantom record in DynamoDB -> Flush to CLOSED
                    item['exit_status'] = 'CLOSED (RECONCILED_BROKER_EXIT)'
                    item['exit_timestamp'] = dt.now().strftime("%Y-%m-%d %H:%M:%S")
                    batch.put_item(Item=item)
                    print(f"🔄 [RECONCILE DYNAMO] Pruned phantom trade: {occ} (Trade ID: {item.get('trade_id')})")

        # Adopt new positions found on Tradier
        dynamo_active_syms = {it.get('occ_symbol', it.get('ticker')) for it in dynamo_active}
        for sym, pos in broker_positions.items():
            if sym not in dynamo_active_syms:
                match = re.match(r'^([A-Z]+)\d{6}[CP]\d{8}$', sym)
                ticker = match.group(1) if match else sym[:4].rstrip('0123456789')
                cost_basis = float(pos.get('cost_basis', 0.0))
                qty = float(pos.get('quantity', 1))
                entry_px = round(cost_basis / (qty * 100.0), 2) if (cost_basis > 10.0 and qty > 0) else round(cost_basis / qty, 2)

                t_id = f"adopt_{sym.lower()}_{dt.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}"
                new_item = {
                    'tenant_id': tenant_id,
                    'trade_id': t_id,
                    'occ_symbol': sym,
                    'ticker': ticker,
                    'shares': str(int(qty)),
                    'entry_price': str(entry_px),
                    'cost_basis': str(entry_px),
                    'exit_status': 'ACTIVE',
                    'direction': 'CALL' if 'C' in sym[len(ticker):] else 'PUT',
                    'timestamp': dt.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'execution_tag': 'BROKER_ADOPTED',
                    'cso_notes': 'ADOPTED_FROM_TRADIER'
                }
                table.put_item(Item=new_item)
                print(f"[✓] [RECONCILE DYNAMO] Adopted Tradier position: {sym} ({int(qty)}x @ ${entry_px})")
    except Exception as e:
        print(f"[-] Broker Reconciler: DynamoDB sync error: {e}")

    # 3. Reconcile Local SQLite
    if os.path.exists(DB_FILE):
        try:
            conn = sqlite3.connect(DB_FILE, timeout=5.0)
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            
            # Prune phantom records
            c.execute("SELECT id, ticker, occ_symbol FROM trades WHERE exit_status = 'ACTIVE'")
            active_sq = c.fetchall()
            for r in active_sq:
                occ = r['occ_symbol'] or r['ticker']
                if occ not in broker_positions:
                    c.execute("""
                        UPDATE trades 
                        SET exit_status = 'CLOSED (RECONCILED_BROKER_EXIT)', exit_timestamp = ? 
                        WHERE id = ?
                    """, (dt.now().strftime("%Y-%m-%d %H:%M:%S"), r['id']))
                    print(f"🔄 [RECONCILE SQLITE] Pruned phantom trade: {occ} (Row ID: {r['id']})")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[-] Broker Reconciler: SQLite sync error: {e}")

    return broker_positions

if __name__ == "__main__":
    print("[*] Running authoritative broker reconciliation test...")
    holdings = reconcile_broker_state()
    print(f"[✓] Complete. Active positions on Tradier: {len(holdings)}")
