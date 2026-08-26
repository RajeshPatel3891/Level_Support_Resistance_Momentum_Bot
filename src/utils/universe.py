import glob
import json
import os

def get_playbook_tickers():
    """Dynamically discover all playbook tickers from src/playbooks/"""
    return [
        os.path.basename(f).replace("_playbook.py", "").upper()
        for f in glob.glob("src/playbooks/*_playbook.py")
    ]

def get_active_universe():
    """Dynamically read active ticker universe from trading_levels.json"""
    if os.path.exists("trading_levels.json"):
        try:
            with open("trading_levels.json", "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data:
                    return list(data.keys())
        except Exception:
            pass
    return get_playbook_tickers()
