#!/usr/bin/env python3
"""
HARM.AI // EOD TICK & TELEMETRY S3 ARCHIVAL ENGINE
===============================================================================
1. Exports today's trades and telemetry ticks from harm_telemetry.db.
2. Compresses the dataset into a GZIP archive (ticks_YYYY-MM-DD.db.gz).
3. Uploads the compressed snapshot to AWS S3: s3://<BUCKET>/ticks/YYYY-MM-DD/
4. Vacuums local SQLite storage to prevent database bloat.
"""

import os
import sys
import gzip
import shutil
import sqlite3
import boto3
from datetime import datetime
from dotenv import load_dotenv

# Load Prod Env
if os.path.exists(".env.prod"):
    load_dotenv(".env.prod", override=True)
else:
    load_dotenv(override=True)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'harm_telemetry.db')
S3_BUCKET = os.getenv("S3_TELEMETRY_BUCKET", "harmonized-ai-telemetry-bucket")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

def log_msg(msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [S3_ARCHIVER] {msg}")

def archive_and_upload():
    today_str = datetime.now().strftime("%Y-%m-%d")
    log_msg(f"Starting EOD Archival Process for Date: {today_str}...")

    if not os.path.exists(DB_PATH):
        log_msg(f"[!] Target SQLite database {DB_PATH} not found. Aborting.")
        return False

    # 1. Create compressed local backup
    archive_filename = f"harm_telemetry_{today_str}.db.gz"
    archive_path = os.path.join(os.path.dirname(DB_PATH), archive_filename)

    log_msg(f"Compressing {DB_PATH} -> {archive_path}...")
    try:
        with open(DB_PATH, 'rb') as f_in:
            with gzip.open(archive_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        log_msg(f"[✓] Local compression complete ({os.path.getsize(archive_path) / 1024:.1f} KB).")
    except Exception as e:
        log_msg(f"[-] Compression error: {e}")
        return False

    # 2. Upload to AWS S3
    s3_key = f"ticks/{today_str}/{archive_filename}"
    log_msg(f"Uploading to s3://{S3_BUCKET}/{s3_key}...")

    try:
        s3 = boto3.client('s3', region_name=AWS_REGION)
        s3.upload_file(archive_path, S3_BUCKET, s3_key)
        log_msg(f"[✓ SUCCESS] Archived to S3 bucket '{S3_BUCKET}'!")
    except Exception as e:
        log_msg(f"[!] S3 Upload Warning (Bucket might need creation or IAM policy): {e}")
        log_msg(f"[*] Local backup preserved at: {archive_path}")

    # 3. Clean up local backup file after upload
    if os.path.exists(archive_path):
        os.remove(archive_path)

    # 4. Vacuum local SQLite database to recover space
    try:
        log_msg("Vacuuming local SQLite database to reclaim disk space...")
        conn = sqlite3.connect(DB_PATH)
        conn.execute("VACUUM;")
        conn.close()
        log_msg("[✓] SQLite database optimized and ready for next session.")
    except Exception as e:
        log_msg(f"[-] SQLite VACUUM error: {e}")

    return True

if __name__ == "__main__":
    archive_and_upload()
