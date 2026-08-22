import os, json

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "strategy_config.json")

DEFAULT_CONFIG = {
    "execution_guards": {
        "min_dte_default": 3,
        "low_price_stock_threshold": 30.00,
        "low_price_stock_min_dte": 7,
        "max_ask_bid_spread_pct": 0.15,
        "late_day_entry_cutoff_et": "15:30",
        "max_trade_dollar_cost": 100.00
    },
    "tactical_strategies": {
        "green_stays_green": {
            "enabled": True,
            "activation_time_et": "15:15",
            "trail_stop_pct": 0.10
        }
    }
}

def load_strategy_config():
    if not os.path.exists(CONFIG_PATH):
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r") as f:
            user_cfg = json.load(f)
            # Merge with default fallback for missing keys
            merged = DEFAULT_CONFIG.copy()
            for k, v in user_cfg.items():
                if isinstance(v, dict) and k in merged:
                    merged[k].update(v)
                else:
                    merged[k] = v
            return merged
    except Exception as e:
        print(f"[!] Config load warning: {e}. Defaulting to safe hardcoded strategy config.")
        return DEFAULT_CONFIG
