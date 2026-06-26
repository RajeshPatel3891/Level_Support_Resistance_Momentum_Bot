import csv

# Color codes
GREEN = '\033[92m'
RED = '\033[91m'
BOLD = '\033[1m'
RESET = '\033[0m'

print(f"{BOLD}{'TIME':<17} | {'TICKER':<6} | {'SIDE':<5} | {'PnL':<7} | {'EMO':<3} | {'NOTES'}{RESET}")
print("-" * 80)

try:
    with open('TradeLog.csv', 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                pnl_val = float(row['PnL'])
                color = GREEN if pnl_val >= 0 else RED
                emo_icon = "🔥" if int(row['EmotionalScore']) > 5 else "✅"
                print(f"{row['Timestamp']:<17} | {row['Ticker']:<6} | {row['Side']:<5} | {color}{pnl_val:>+7.2f}{RESET} | {emo_icon}{row['EmotionalScore']:<2} | {row['Notes']}")
            except (ValueError, KeyError):
                continue
except FileNotFoundError:
    print("Error: TradeLog.csv not found.")
