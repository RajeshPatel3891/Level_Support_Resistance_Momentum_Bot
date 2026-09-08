#!/usr/bin/env python3
import os, sys, gzip, shutil, boto3, argparse

def download_and_extract(bucket_name, date_str, output_db="replay_telemetry.db"):
    s3 = boto3.client("s3")
    key = f"telemetry/harm_telemetry_{date_str}.db.gz"
    gz_tmp = f"/tmp/telemetry_{date_str}.db.gz"

    print(f"[*] Downloading s3://{bucket_name}/{key}...")
    try:
        s3.download_file(bucket_name, key, gz_tmp)
    except Exception as e:
        print(f"[!] S3 Download failed: {e}")
        sys.exit(1)

    print(f"[*] Unpacking archive to {output_db}...")
    with gzip.open(gz_tmp, 'rb') as f_in:
        with open(output_db, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)

    if os.path.exists(gz_tmp):
        os.remove(gz_tmp)
        
    print(f"[✓] Replay database ready: {output_db} ({os.path.getsize(output_db)} bytes)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pull dated telemetry SQLite snapshot from S3")
    parser.add_argument("-b", "--bucket", default="harmonized-ai-telemetry-bucket", help="S3 bucket")
    parser.add_argument("-d", "--date", required=True, help="Date string (YYYY-MM-DD)")
    parser.add_argument("-o", "--output", default="replay_telemetry.db", help="Target SQLite filename")
    args = parser.parse_args()

    download_and_extract(args.bucket, args.date, args.output)
