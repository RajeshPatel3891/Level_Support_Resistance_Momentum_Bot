import json
import sqlite3
import os
import boto3
from datetime import datetime

lambda_client = boto3.client('lambda', region_name='us-east-1')
DB_PATH = 'src/harm_telemetry.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gex_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            underlying_price REAL,
            net_gex REAL,
            gex_label TEXT,
            timestamp TEXT
        )
    ''')
    conn.commit()
    conn.close()

def pull_lambda_telemetry():
    try:
        response = lambda_client.invoke(
            FunctionName='GemmaEX',
            InvocationType='RequestResponse'
        )
        payload = json.loads(response['Payload'].read().decode('utf-8'))
        if payload.get('statusCode') != 200:
            print(f"[-] Lambda returned an error status: {payload.get('statusCode')}")
            return None
        body = json.loads(payload.get('body', '{}'))
        return body.get('data', [])
    except Exception as e:
        print(f"[-] Failed to invoke GemmaEX Lambda function: {e}")
        return None

def log_to_database(data_records):
    if not data_records:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    inserted_count = 0
    for record in data_records:
        cursor.execute('''
            INSERT INTO gex_telemetry (ticker, underlying_price, net_gex, gex_label, timestamp)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            record['ticker'],
            record['underlying_price'],
            record['net_gex'],
            record['gex_label'],
            record['timestamp']
        ))
        inserted_count += 1
    conn.commit()
    conn.close()
    print(f"[+] Successfully logged {inserted_count} ticker metrics to {DB_PATH} at {datetime.now()}")

if __name__ == '__main__':
    print("[*] Launching GemmaEX Telemetry Bridge...")
    init_db()
    records = pull_lambda_telemetry()
    if records:
        log_to_database(records)
    else:
        print("[-] No records fetched.")
