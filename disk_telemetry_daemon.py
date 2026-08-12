import os
import time
import shutil
import subprocess
import glob
from datetime import datetime, timedelta
import boto3
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv('AWS_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table('HarmonizedTrades')

CHECK_INTERVAL_SECONDS = 1800  # Check every 30 minutes
MIN_FREE_GB = 3.0              # Trigger cleanup if free space drops below 3 GB
RETENTION_DAYS = 5             # Purge local logs/backups older than 5 days

def cleanup_old_files():
    """Purge local logs, old SQLite backups, and temp files older than 5 days."""
    cutoff = time.time() - (RETENTION_DAYS * 86400)
    cleaned_count = 0
    
    # 1. Clean old backup files
    for path in glob.glob('backups/*.db') + glob.glob('*.db-journal'):
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                cleaned_count += 1
        except Exception:
            pass
            
    # 2. Clean old log files
    for path in glob.glob('logs/*.log') + glob.glob('*.log'):
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                cleaned_count += 1
        except Exception:
            pass
            
    if cleaned_count > 0:
        print(f"[DISK GUARDIAN] Purged {cleaned_count} expired local files (> {RETENTION_DAYS} days old).")

def run_disk_daemon():
    print("==========================================================")
    print("🛡️ BACKGROUND DISK TELEMETRY & RETENTION DAEMON ACTIVE")
    print("==========================================================")

    while True:
        try:
            # Check disk usage
            total, used, free = shutil.disk_usage("/")
            free_gb = free / (1024 ** 3)
            used_pct = (used / total) * 100
            
            print(f"[DISK GUARDIAN] Status -> Free: {free_gb:.2f} GB ({100 - used_pct:.1f}% available)")

            # Enforce 5-day retention cleanup
            cleanup_old_files()

            # If free space is critically low, prune Docker system
            if free_gb < MIN_FREE_GB:
                print(f"⚠️ [DISK ALERT] Free space ({free_gb:.2f} GB) below threshold ({MIN_FREE_GB} GB). Pruning Docker cache...")
                subprocess.run("docker system prune -af --volumes", shell=True, capture_output=True)
                
                # Re-check
                _, _, free_after = shutil.disk_usage("/")
                print(f"[DISK GUARDIAN] Post-prune Free Space: {free_after / (1024 ** 3):.2f} GB")

        except Exception as e:
            print(f"[!] Disk Daemon Error: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == '__main__':
    run_disk_daemon()
