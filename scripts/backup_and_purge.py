import os
import json
import gzip
import boto3
from datetime import datetime

def run_backup_and_purge():
    date_tag = datetime.now().strftime('%Y-%m-%d')
    print(f"[*] Starting Harmonized AI Backup & Purge Sequence [{date_tag}]...")

    s3 = boto3.client('s3', region_name='us-east-1')
    bucket_name = 'harmonized-ai-telemetry-bucket'

    # 1. DynamoDB Export & S3 Upload
    try:
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.Table('HarmonizedTrades')
        
        response = table.scan()
        items = response.get('Items', [])
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))

        json_filename = f'dynamodb_trades_{date_tag}.json'
        with open(json_filename, 'w') as f:
            json.dump(items, f, indent=2, default=str)

        gz_filename = f'{json_filename}.gz'
        with open(json_filename, 'rb') as f_in:
            with gzip.open(gz_filename, 'wb') as f_out:
                f_out.writelines(f_in)

        s3.upload_file(gz_filename, bucket_name, f'dynamodb_backup/{gz_filename}')
        print(f"[✓] DynamoDB backup uploaded to S3: {gz_filename}")
        
        # Clean local temp files
        if os.path.exists(json_filename): os.remove(json_filename)
        if os.path.exists(gz_filename): os.remove(gz_filename)

        # Purge closed records from DynamoDB
        purged_count = 0
        for item in items:
            if str(item.get('exit_status', '')).startswith('CLOSED') or '[SCJ]' in str(item.get('exit_status', '')) or 'EXPIRED' in str(item.get('exit_status', '')):
                table.delete_item(Key={'tenant_id': item['tenant_id'], 'trade_id': item['trade_id']})
                purged_count += 1
        print(f"[✓] Purged {purged_count} closed historical records from DynamoDB.")
    except Exception as e:
        print(f"[-] Error in DynamoDB backup/purge: {e}")

    # 2. SQLite Telemetry Backup & S3 Upload
    try:
        db_path = 'harm_telemetry.db'
        if os.path.exists(db_path):
            backup_name = f'harm_telemetry_{date_tag}.db.gz'
            with open(db_path, 'rb') as f_in:
                with gzip.open(backup_name, 'wb') as f_out:
                    f_out.writelines(f_in)
            
            s3.upload_file(backup_name, bucket_name, f'telemetry/{backup_name}')
            print(f"[✓] SQLite telemetry backup uploaded to S3: {backup_name}")
            if os.path.exists(backup_name): os.remove(backup_name)
    except Exception as e:
        print(f"[-] Error in SQLite telemetry backup: {e}")

if __name__ == "__main__":
    run_backup_and_purge()
