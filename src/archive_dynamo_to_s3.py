#!/usr/bin/env python3
import os
import sys
import json
import gzip
import datetime
import boto3
from decimal import Decimal

S3_BUCKET = "harmonized-ai-telemetry-bucket"
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_NAME = "HarmonizedTrades"

class DecimalEncoder(json.JSONEncoder):
    """Convert DynamoDB Decimal types to float/int for JSON serialization."""
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o) if o % 1 else int(o)
        return super(DecimalEncoder, self).default(o)

def archive_dynamodb_to_s3():
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    gz_filename = f"dynamodb_trades_{today_str}.json.gz"
    s3_key = f"dynamodb/{today_str}/{gz_filename}"

    print("=" * 65)
    print("📦 HARM.AI // DYNAMODB TABLE S3 ARCHIVAL PIPELINE")
    print(f"   Source Table : {TABLE_NAME}")
    print(f"   Target S3    : s3://{S3_BUCKET}/{s3_key}")
    print("=" * 65)

    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    table = dynamodb.Table(TABLE_NAME)

    print("[*] Step 1: Scanning DynamoDB table records...")
    try:
        response = table.scan()
        items = response.get('Items', [])
        
        while 'LastEvaluatedKey' in response:
            response = table.scan(ExclusiveStartKey=response['LastEvaluatedKey'])
            items.extend(response.get('Items', []))
            
        print(f"[✓] Successfully scanned {len(items)} items from DynamoDB.")
    except Exception as e:
        print(f"[❌ FATAL] DynamoDB scan failed: {e}")
        sys.exit(1)

    print("[*] Step 2: Compressing records to JSON archive...")
    try:
        with gzip.open(gz_filename, 'wt', encoding='utf-8') as f_out:
            for item in items:
                f_out.write(json.dumps(item, cls=DecimalEncoder) + '\n')
        
        size_mb = os.path.getsize(gz_filename) / (1024 * 1024)
        print(f"[✓] Compression complete: {size_mb:.2f} MB")
    except Exception as e:
        print(f"[❌ FATAL] Compression failed: {e}")
        sys.exit(1)

    print("[*] Step 3: Uploading archive to S3...")
    s3_client = boto3.client('s3', region_name=AWS_REGION)
    try:
        s3_client.upload_file(gz_filename, S3_BUCKET, s3_key)
        print(f"[✓] Upload successful: s3://{S3_BUCKET}/{s3_key}")
    except Exception as e:
        print(f"[❌ FATAL] S3 upload failed: {e}")
        if os.path.exists(gz_filename):
            os.remove(gz_filename)
        sys.exit(1)

    if os.path.exists(gz_filename):
        os.remove(gz_filename)
        print(f"[✓] Cleaned up temporary local archive '{gz_filename}'.")

    print("\n[🎉] DYNAMODB ARCHIVE COMPLETE. DATA SECURED ON S3.")

if __name__ == "__main__":
    archive_dynamodb_to_s3()
