import os
import json

def get_live_levels(ticker):
    """
    Safely loads the master trading_levels.json manifest from the project root
    and returns the level parameters for the requested ticker asset.
    """
    # Locate the manifest in the parent/root directory relative to this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    manifest_path = os.path.join(parent_dir, 'trading_levels.json')
    
    # Fallback to local folder lookup if path trees vary
    if not os.path.exists(manifest_path):
        manifest_path = os.path.join(current_dir, 'trading_levels.json')
        
    if not os.path.exists(manifest_path):
        print(f"[-] LEVEL LOADER WARNING: Manifest missing at {manifest_path}. Returning default mapping structure.")
        return {}
        
    try:
        with open(manifest_path, 'r') as f:
            data = json.load(f)
            return data.get(ticker, {})
    except Exception as e:
        print(f"[!] LEVEL LOADER ERROR: Failed reading manifest levels: {e}")
        return {}
