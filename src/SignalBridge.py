import json
import fcntl
import os

SIGNAL_FILE = 'active_signals.json'

def init_bridge():
    """Initializes the bridge file if it doesn't exist."""
    if not os.path.exists(SIGNAL_FILE):
        with open(SIGNAL_FILE, 'w') as f:
            json.dump([], f)
        print(f"[*] Initialized Signal Bridge at {SIGNAL_FILE}")

def read_signals():
    """Reads signals from the bridge, ensuring a list is returned, with locking."""
    if not os.path.exists(SIGNAL_FILE):
        return []
    with open(SIGNAL_FILE, 'r') as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            data = json.load(f)
            # If the poller wrote a single dict, return it as a list of one
            return [data] if isinstance(data, dict) else data
        except json.JSONDecodeError:
            return []
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)

def write_signals(signals):
    """Writes the current signal state to the bridge with locking."""
    with open(SIGNAL_FILE, 'w') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            json.dump(signals, f, indent=4)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
