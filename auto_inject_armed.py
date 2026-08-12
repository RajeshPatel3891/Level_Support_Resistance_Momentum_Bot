
def validate_option_spread(quote, max_spread_pct=0.02):
    '''Reject option entries if the Bid-Ask spread exceeds max_spread_pct (default 2%).'''
    bid = float(quote.get('bid') or 0.0)
    ask = float(quote.get('ask') or 0.0)
    if ask <= 0 or bid <= 0:
        print(f"[⚠️ SPREAD GUARD] Invalid quotes for option: Bid=${bid}, Ask=${ask}")
        return False, 0.0
    
    spread_pct = (ask - bid) / ask
    if spread_pct > max_spread_pct:
        print(f"[⛔ SPREAD REJECT] Spread too wide ({spread_pct*100.0:.1f}% > {max_spread_pct*100.0:.1f}%). Bid=${bid}, Ask=${ask}")
        return False, bid
    
    return True, ask

import os
import sys
import json
import boto3
import requests
import subprocess
from datetime import datetime

def get_fargate_public_ip():
    """Queries AWS ECS and EC2 APIs to discover active Fargate Task Public IP."""
    try:
        ecs = boto3.client('ecs', region_name='us-east-1')
        ec2 = boto3.client('ec2', region_name='us-east-1')
        
        tasks = ecs.list_tasks(cluster='harmonized-cluster').get('taskArns', [])
        if not tasks:
            return None
            
        task_desc = ecs.describe_tasks(cluster='harmonized-cluster', tasks=[tasks[0]]).get('tasks', [])[0]
        attachments = task_desc.get('attachments', [])[0].get('details', [])
        
        eni_id = None
        for d in attachments:
            if d.get('name') == 'networkInterfaceId':
                eni_id = d.get('value')
                break
                
        if eni_id:
            eni_desc = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
            public_ip = eni_desc['NetworkInterfaces'][0].get('Association', {}).get('PublicIp')
            return public_ip
    except Exception as e:
        print(f"[!] Unable to resolve Fargate Public IP via AWS SDK: {e}")
    return None

def run_armed_injection():
    print("==========================================================")
    print("🦅 HARM.AI // AUTOMATED CSO INJECTOR DAEMON")
    print("==========================================================")
    
    ip = get_fargate_public_ip()
    proximity_data = {}
    
    # 1. Query live Fargate API endpoint across both port 8080 and 8000
    if ip:
        for port in [8080, 8000]:
            url = f"http://{ip}:{port}/api/proximity"
            try:
                print(f"[*] Querying Fargate API at {url}...")
                resp = requests.get(url, timeout=4)
                if resp.status_code == 200 and isinstance(resp.json(), dict):
                    proximity_data = resp.json()
                    print(f"[✓] Successfully retrieved live proximity matrix from Fargate ({ip}:{port})!")
                    break
            except Exception:
                continue

    # 2. Fallback to local trading_levels.json if Fargate network query fails
    if not proximity_data and os.path.exists("trading_levels.json"):
        print("[!] Falling back to local trading_levels.json...")
        try:
            with open("trading_levels.json", "r") as f:
                data = json.load(f)
            levels = data.get("levels", data) if isinstance(data, dict) else {}
            
            for ticker, details in levels.items():
                if not isinstance(details, dict):
                    continue
                spot = float(details.get("spot") or details.get("last_price") or 0.0)
                
                target_val = 0.0
                if "algo_macro" in details and isinstance(details["algo_macro"], dict):
                    target_list = details["algo_macro"].get("target", ["$0.00"])
                    target_str = target_list[0] if target_list else "$0.00"
                    try:
                        target_val = float(str(target_str).replace("$", "").replace(",", ""))
                    except ValueError:
                        target_val = 0.0
                
                gap_val = abs(spot - target_val) if target_val > 0 else 0.0
                gap_pct = (gap_val / spot * 100.0) if spot > 0 and target_val > 0 else 999.0
                
                proximity_data[ticker] = {
                    "armed": (gap_pct <= 1.0),
                    "status": "ARMED" if gap_pct <= 1.0 else "WAITING"
                }
        except Exception as e:
            print(f"[!] Error parsing local levels: {e}")

    # 3. Identify ARMED tickers
    armed_tickers = [
        ticker for ticker, info in proximity_data.items()
        if isinstance(info, dict) and (info.get("armed") is True or info.get("status") == "ARMED")
    ]

    if not armed_tickers:
        print("[ℹ️] No tickers are currently ARMED. Injection loop completed.")
        return

    print(f"\n🎯 Identified {len(armed_tickers)} ARMED Ticker(s): {armed_tickers}\n")

    # 4. Trigger smart_cso_injector.py for each armed ticker
    for ticker in armed_tickers:
        print(f"🚀 Triggering CSO Live Injection for: {ticker}...")
        cmd = [sys.executable, "src/smart_cso_injector.py", "--ticker", ticker]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                print(f"[✓] {ticker} Injector Output:\n{res.stdout.strip()}\n")
            else:
                print(f"[!] {ticker} Injector Output (Exit Code {res.returncode}):\n{res.stderr.strip() or res.stdout.strip()}\n")
        except Exception as ex:
            print(f"[!] Error executing injector script for {ticker}: {ex}\n")

if __name__ == "__main__":
    run_armed_injection()
