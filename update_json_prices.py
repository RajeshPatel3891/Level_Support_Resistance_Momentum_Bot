import json, time, re

# Sync live prices into trading_levels.json every 2 seconds
price_file = "trading_levels.json"

while True:
    try:
        # Read latest prices from tmux logs
        import subprocess
        log_out = subprocess.check_output("tmux capture-pane -pt harm_live_stack:0 -p | tail -n 50", shell=True).decode()
        
        hits = re.findall(r'\[\+\] TICKER HIT -> ([A-Z]+): \$([0-9\.]+)', log_out)
        
        if hits:
            with open(price_file, 'r') as f:
                levels = json.load(f)
                
            updated = False
            for ticker, price in hits:
                if ticker in levels:
                    levels[ticker]['last_price'] = float(price)
                    updated = True
                    
            if updated:
                with open(price_file, 'w') as f:
                    json.dump(levels, f, indent=2)
    except Exception as e:
        pass
    time.sleep(2)
