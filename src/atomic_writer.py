import json
import os
import tempfile

def save_json_atomically(data, filepath="trading_levels.json"):
    """
    Safely writes JSON data to a temporary file in the target directory 
    before atomically replacing the destination file via OS-level swap.
    Guards against 0-byte file truncation on disk-full errors.
    """
    dirname = os.path.dirname(filepath) or "."
    with tempfile.NamedTemporaryFile("w", dir=dirname, delete=False) as tf:
        json.dump(data, tf, indent=2)
        temp_name = tf.name
    
    os.replace(temp_name, filepath)
