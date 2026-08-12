import os
import boto3
from dotenv import load_dotenv

load_dotenv()

def hard_purge_all():
    print("==========================================================")
    print("🔥 HARM.AI // HARD SYSTEM PURGE & COMPLETE RESET")
    print("==========================================================")

    region = os.getenv('AWS_REGION', 'us-east-1')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table('HarmonizedTrades')

    key_schema = table.key_schema
    key_names = [k['AttributeName'] for k in key_schema]
    print(f"[*] Detected DynamoDB Key Schema: {key_names}")

    print("[1/3] Deleting ALL records from DynamoDB HarmonizedTrades...")
    try:
        response = table.scan()
        items = response.get('Items', [])
        for item in items:
            key_dict = {k: item[k] for k in key_names if k in item}
            print(f"    -> Deleting trade record {key_dict} from DynamoDB...")
            table.delete_item(Key=key_dict)
        print("[✓] DynamoDB table completely wiped clean.")
    except Exception as e:
        print(f"[!] Error wiping DynamoDB: {e}")

    print("[2/3] Rebuilding local SQLite database and clearing ledgers...")
    os.system("python3 rebuild_db.py")
    os.system("python3 preboot_db_fix.py")

    print("[3/3] Purging temporary logs, cache, and dashboard state...")
    os.system("rm -rf logs/*.log *.log dashboard_data.json")

    print("==========================================================")
    print("[✓] HARD PURGE COMPLETE. MATH RESET TO ZERO. READY FOR FRESH START!")
    print("==========================================================")

if __name__ == '__main__':
    hard_purge_all()
