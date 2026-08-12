import sqlite3
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "harm_telemetry.db"

def purge_local_closed():
    if not os.path.exists(DB_PATH):
        print("[!] Local SQLite database not found.")
        return 0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Delete only non-active (closed/exited) rows, leaving active positions safe
    cursor.execute("DELETE FROM trades WHERE exit_status != 'ACTIVE';")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"[✓] Purged {deleted} closed trade records from local SQLite.")
    return deleted

def purge_dynamo_closed():
    try:
        dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        table = dynamodb.Table('HarmonizedTrades')
        
        res = table.scan()
        items = res.get('Items', [])
        
        count = 0
        for item in items:
            if item.get('exit_status', 'ACTIVE') != 'ACTIVE':
                table.delete_item(
                    Key={
                        'tenant_id': item.get('tenant_id', 'default'),
                        'trade_id': item.get('trade_id')
                    }
                )
                count += 1
                
        print(f"[✓] Purged {count} closed trade records from AWS DynamoDB HarmonizedTrades.")
    except Exception as e:
        print(f"[-] DynamoDB purge warning: {e}")

if __name__ == "__main__":
    print("[*] Starting clean slate purge for closed trade history...")
    purge_local_closed()
    purge_dynamo_closed()
    
    # Re-compile dashboard data immediately
    import subprocess
    subprocess.run(["python3", "src/generate_dashboard_data.py"], check=False)
    print("[✓] Dashboard telemetry re-compiled successfully with clean history.")
