import boto3
import re
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

def run_replay_session():
    region = os.getenv('AWS_REGION', 'us-east-1')
    log_group = "/ecs/harmonized-trading-engine"
    
    print("==========================================================")
    print("📜 CLOUDWATCH LOG-DRIVEN TICK REPLAY & AUDIT ENGINE")
    print(f"📡 LOG GROUP: {log_group} ({region})")
    print("==========================================================")

    # 1. Fetch Active Positions from DynamoDB
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table('HarmonizedTrades')
    res = table.scan()
    items = res.get('Items', [])

    active_items = [i for i in items if str(i.get('exit_status', '')).upper() == 'ACTIVE']

    if not active_items:
        print("❌ [!] No active positions found in DynamoDB.")
        return

    portfolio = {}
    for i in active_items:
        tkr = str(i.get('ticker', '')).upper()
        entry = float(i.get('entry_price', 0.80) or 0.80)
        shares = float(i.get('shares', 1.0) or 1.0)
        
        portfolio[tkr] = {
            'entry': entry,
            'shares': shares,
            'peak_mark': entry,
            'peak_pnl': 0.0,
            'current_mark': entry,
            'gsg_triggered': False,
            'min_dollar_gsg_hit': False,
            'gsg_hit_time': None
        }

    print(f"[✓] Synced {len(portfolio)} active positions: {list(portfolio.keys())}")

    # 2. Fetch Log Events from CloudWatch (Past 2 Hours)
    cw_client = boto3.client('logs', region_name=region)
    start_time = int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp() * 1000)

    print("[*] Pulling tick logs from AWS CloudWatch...")
    
    ticks_parsed = 0
    try:
        paginator = cw_client.get_paginator('filter_log_events')
        page_iterator = paginator.paginate(
            logGroupName=log_group,
            startTime=start_time,
            filterPattern='MONITOR'
        )

        # Regex patterns to catch logged marks and prices
        mark_pattern = re.compile(r"\((\w+)\)\s*\|\s*Entry:\s*\$([\d\.]+).*?(?:Mark|Price|Live)?:\s*\$([\d\.]+)", re.IGNORECASE)
        alt_pattern = re.compile(r"(\w+)\s+mark:\s*\$([\d\.]+)", re.IGNORECASE)

        for page in page_iterator:
            for event in page.get('events', []):
                msg = event['message']
                ts = datetime.fromtimestamp(event['timestamp'] / 1000.0).strftime('%H:%M:%S')

                # Try matching primary monitor log lines
                match = mark_pattern.search(msg)
                if match:
                    tkr, entry_px, mark_px = match.group(1).upper(), float(match.group(2)), float(match.group(3))
                    if tkr in portfolio:
                        ticks_parsed += 1
                        update_portfolio(portfolio[tkr], tkr, mark_px, ts)
                        continue

                # Fallback pattern match
                for tkr in portfolio.keys():
                    if re.search(r"\b" + tkr + r"\b", msg.upper()):
                        nums = re.findall(r"\$([\d\.]+)", msg)
                        if nums:
                            mark_px = float(nums[-1])
                            ticks_parsed += 1
                            update_portfolio(portfolio[tkr], tkr, mark_px, ts)

    except Exception as e:
        print(f"⚠️ [!] CloudWatch Log Fetch Warning: {e}")

    print(f"[✓] Processed {ticks_parsed} tick events from Fargate runtime logs.\n")

    # 3. Output Replay Summary Table
    print(f"{'TICKER':<8} | {'ENTRY':<7} | {'PEAK MARK':<9} | {'PEAK PnL':<10} | {'+$1 GSG FLOOR EXIT':<22} | {'CURRENT PnL':<10}")
    print("-" * 80)

    for tkr, d in portfolio.items():
        entry_str = f"${d['entry']:.2f}"
        peak_str = f"${d['peak_mark']:.2f}"
        peak_pnl_str = f"+${d['peak_pnl']:.2f}"
        
        if d['gsg_triggered']:
            gsg_str = f"LOCKED @ +$1.00 ({d['gsg_hit_time']})"
        elif d['min_dollar_gsg_hit']:
            gsg_str = f"ARMED @ {d['gsg_hit_time']}"
        else:
            gsg_str = "NOT REACHED (< $1)"

        curr_pnl = round((d['current_mark'] - d['entry']) * 100.0 * d['shares'], 2)
        curr_pnl_str = f"{'+' if curr_pnl >= 0 else ''}${curr_pnl:.2f}"

        print(f"{tkr:<8} | {entry_str:<7} | {peak_str:<9} | {peak_pnl_str:<10} | {gsg_str:<22} | {curr_pnl_str:<10}")

    print("==========================================================")

def update_portfolio(d, tkr, price, ts):
    entry = d['entry']
    shares = d['shares']
    d['current_mark'] = price
    pnl = round((price - entry) * 100.0 * shares, 2)

    if price > d['peak_mark']:
        d['peak_mark'] = price
        d['peak_pnl'] = pnl

    # SIMULATION: Min +$1.00 GSG Floor Rule
    if pnl >= 1.00 and not d['min_dollar_gsg_hit']:
        d['min_dollar_gsg_hit'] = True
        d['gsg_hit_time'] = ts

    if d['min_dollar_gsg_hit'] and not d['gsg_triggered'] and pnl <= 1.00:
        d['gsg_triggered'] = True

if __name__ == '__main__':
    run_replay_session()
