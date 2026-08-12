import os
import shutil
import subprocess

def check_and_clean_disk(min_free_gb=2.0):
    print("[*] Running automated disk space inspection...")
    
    # Check root disk usage
    total, used, free = shutil.disk_usage("/")
    free_gb = free / (1024 ** 3)
    used_pct = (used / total) * 100
    
    print(f"    -> Disk Free: {free_gb:.2f} GB ({100 - used_pct:.1f}% available)")
    
    if free_gb < min_free_gb:
        print(f"⚠️ WARNING: Free disk space ({free_gb:.2f} GB) is below threshold ({min_free_gb} GB). Purging clutter...")
        
        # 1. Remove old backups and logs
        cleaned_files = 0
        for pattern in ['backups/*.db', 'logs/*.log', '*.log']:
            res = subprocess.run(f"rm -rf {pattern}", shell=True, capture_output=True)
            cleaned_files += 1
            
        # 2. Prune Docker build cache and dangling volumes
        print("[*] Pruning Docker build cache and unused volumes...")
        subprocess.run("docker system prune -af --volumes", shell=True, capture_output=True)
        
        # Re-check space after cleanup
        _, _, free_after = shutil.disk_usage("/")
        free_after_gb = free_after / (1024 ** 3)
        print(f"[✓] Cleanup complete. Free space recovered: {free_after_gb:.2f} GB")
    else:
        print("[✓] Disk space is healthy.")

if __name__ == '__main__':
    check_and_clean_disk()
