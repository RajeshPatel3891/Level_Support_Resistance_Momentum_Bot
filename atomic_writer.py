import json
import os

def save_json_atomically(data, target_file="trading_levels.json"):
    """
    Safely writes JSON data to a temporary file first before atomically
    replacing the target file. Prevents 0-byte file truncation on disk-full errors.
    """
    temp_file = f"{target_file}.tmp"
    
    with open(temp_file, "w") as f:
        json.dump(data, f, indent=2)

    os.replace(temp_file, target_file)  # Atomic swap on OS level
