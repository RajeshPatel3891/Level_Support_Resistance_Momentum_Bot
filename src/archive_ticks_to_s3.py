#!/usr/bin/env python3
import os
import sys
import gzip
import shutil
import datetime
import boto3
from botocore.exceptions import ClientError

DB_FILE = "harm_telemetry.db"
S3_BUCKET = "harmonized-ai-telemetry-bucket"
AWS_REGION = "us-east-1"

def archive_telemetry_to_s3():
    if not os.path.exists(DB_FILE):
        print(f"[❌ ERROR] Database file '{DB_FILE}' not found on host!")
        sys.exit(1)

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    gz_filename = f"harm_telemetry_{today_str}.db.gz"
    s3_key = f"ticks/{today_str}/{gz_filename}"

    print("=" * 65)
    print("📦 HARM.AI // TELEMETRY DATABASE S3 ARCHIVAL PIPELINE")
    print(f"   Source DB   : {DB_FILE}")
    print(f"   Compressed  : {gz_filename}")
    print(f"   Target S3   : s3://{S3_BUCKET}/{s3_key}")
    print("=" * 65)

    # Step 1: Compress the SQLite database file
    print("[*] Step 1: Compressing database snapshot...")
    try:
        with open(DB_FILE, 'rb') as f_in:
            with gzip.open(gz_filename, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        compressed_size_mb = os.path.getsize(gz_filename) / (1024 * 1024)
        print(f"[✓] Compression complete. Compressed archive size: {compressed_size_mb:.2f} MB")
    except Exception as e:
        print(f"[❌ FATAL] Database compression failed: {e}")
        sys.exit(1)

    # Step 2: Upload compressed database to S3
    print("[*] Step 2: Uploading archive to S3...")
    s3_client = boto3.client('s3', region_name=AWS_REGION)
    try:
        s3_client.upload_file(gz_filename, S3_BUCKET, s3_key)
        print(f"[✓] Upload successful: s3://{S3_BUCKET}/{s3_key}")
    except ClientError as e:
        print(f"[❌ FATAL] S3 upload failed: {e}")
        if os.path.exists(gz_filename):
            os.remove(gz_filename)
        sys.exit(1)

    # Step 3: Verify S3 object existence
    print("[*] Step 3: Verifying S3 object integrity...")
    try:
        head = s3_client.head_object(Bucket=S3_BUCKET, Key=s3_key)
        uploaded_size_mb = head['ContentLength'] / (1024 * 1024)
        print(f"[✓] Verified on S3! Object size: {uploaded_size_mb:.2f} MB")
    except ClientError as e:
        print(f"[❌ FATAL] Verification failed. Object not found on S3: {e}")
        sys.exit(1)

    # Step 4: Clean up temporary .gz archive locally (preserving original harm_telemetry.db)
    if os.path.exists(gz_filename):
        os.remove(gz_filename)
        print(f"[✓] Cleaned up temporary local file '{gz_filename}'. Original '{DB_FILE}' preserved.")

    print("\n[🎉] TELEMETRY ARCHIVE COMPLETE. S3 DATA SAFELY SECURED.")

if __name__ == "__main__":
    archive_telemetry_to_s3()
