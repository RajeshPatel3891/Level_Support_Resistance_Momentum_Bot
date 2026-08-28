import os
import re
import time
import json
import requests
import boto3

def get_fargate_private_ip(cluster="harmonized-cluster", region="us-east-1"):
    try:
        ecs = boto3.client("ecs", region_name=region)
        ec2 = boto3.client("ec2", region_name=region)
        tasks = ecs.list_tasks(cluster=cluster, desiredStatus="RUNNING")["taskArns"]
        if not tasks:
            return None
        
        task_detail = ecs.describe_tasks(cluster=cluster, tasks=[tasks[0]])["tasks"][0]
        eni_id = None
        for attachment in task_detail.get("attachments", []):
            for detail in attachment.get("details", []):
                if detail.get("name") == "networkInterfaceId":
                    eni_id = detail.get("value")
                    break
        
        if eni_id:
            eni_detail = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])
            return eni_detail["NetworkInterfaces"][0]["PrivateIpAddress"]
    except Exception as e:
        pass
    return None

def parse_option_symbol(symbol):
    match = re.match(r"^([A-Z]+)(\d{6})([CP])(\d{8})$", symbol)
    if match:
        ticker, date_str, opt_type_letter, strike_raw = match.groups()
        opt_type = "CALL" if opt_type_letter == "C" else "PUT"
        strike = float(strike_raw) / 1000.0
        return ticker, f"{opt_type} ${strike:.2f}", opt_type
    return symbol, "STOCK", "STOCK"

def poll_pnl_loop(env="SANDBOX", interval=2.5):
    if env.upper() == "PROD":
        token = "fyR75AACwlIYhkMyev1doRh6gnSr"
        acct = "6YB87601"
        base_url = "https://api.tradier.com/v1"
    else:
        token = "hcY1t0sY8RZmcsfVjQCA41ecAkFT"
        acct = "VA83416608"
        base_url = "https://sandbox.tradier.com/v1"

    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    
    fargate_ip = get_fargate_private_ip()

    while True:
        try:
            os.system('clear')
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S ET")
            print("==========================================================================================================")
            print(f"📊 LIVE PNL & DYNAMIC FARGATE GEX MONITOR | {env.upper()} ({acct}) | {timestamp}")
            print(f"🔗 TARGET ENGINE IP: {fargate_ip if fargate_ip else 'OFFLINE'}")
            print("==========================================================================================================")

            # Query Live GEX state directly from Fargate Private IP
            gex_levels = {}
            if fargate_ip:
                try:
                    res = requests.get(f"http://{fargate_ip}:8080/api/proximity", timeout=1.5).json()
                    if isinstance(res, dict):
                        gex_levels = res
                except Exception:
                    pass

            pos_res = requests.get(f"{base_url}/accounts/{acct}/positions", headers=headers, timeout=2).json()
            positions = pos_res.get("positions")
            positions = positions.get("position", []) if (positions and positions != "null") else []
            if isinstance(positions, dict): positions = [positions]

            if positions:
                option_symbols = [p.get("symbol") for p in positions if p.get("symbol")]
                underlying_symbols = list(set([parse_option_symbol(s)[0] for s in option_symbols]))
                all_query_symbols = ",".join(option_symbols + underlying_symbols)

                quotes_dict = {}
                try:
                    q_res = requests.get(f"{base_url}/markets/quotes", params={"symbols": all_query_symbols}, headers=headers, timeout=2).json()
                    quotes = q_res.get("quotes", {}).get("quote", [])
                    if isinstance(quotes, dict): quotes = [quotes]
                    for q in quotes:
                        quotes_dict[q.get("symbol")] = {
                            "last": q.get("last", 0) or q.get("close", 0) or 0,
                            "bid": q.get("bid", 0) or q.get("last", 0) or 0
                        }
                except Exception:
                    pass

                total_cost, total_val = 0, 0
                print(f"{'SYMBOL':<22} | {'TYPE':<11} | {'QTY':<4} | {'COST BASIS':<10} | {'BID/LAST':<8} | {'MARKET VAL':<10} | {'GEX EXIT':<11} | {'LIVE PNL'}")
                print("-" * 116)

                for p in positions:
                    sym = p.get("symbol")
                    underlying, opt_desc, opt_type = parse_option_symbol(sym)
                    qty = float(p.get("quantity", 0))
                    cost_basis = float(p.get("cost_basis", 0))
                    
                    opt_bid = quotes_dict.get(sym, {}).get("bid", 0)
                    underlying_spot = quotes_dict.get(underlying, {}).get("last", 0)
                    
                    # Target exact API key schema: target_call & target_put
                    gex_info = gex_levels.get(underlying, {})
                    call_tgt = float(gex_info.get("target_call", 0) or gex_info.get("call_target", 0))
                    put_tgt = float(gex_info.get("target_put", 0) or gex_info.get("put_target", 0))

                    gex_status = "WAITING"
                    if opt_type == "CALL":
                        if call_tgt > 0 and underlying_spot >= call_tgt:
                            gex_status = "🔥 ENGAGED"
                        elif call_tgt > 0 and underlying_spot >= (call_tgt * 0.995):
                            gex_status = "⚡ ARMED"
                    elif opt_type == "PUT":
                        if put_tgt > 0 and underlying_spot <= put_tgt:
                            gex_status = "🔥 ENGAGED"
                        elif put_tgt > 0 and underlying_spot <= (put_tgt * 1.005):
                            gex_status = "⚡ ARMED"

                    current_val = opt_bid * qty * 100 if opt_bid > 0 else cost_basis
                    pnl = current_val - cost_basis
                    pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
                    
                    total_cost += cost_basis
                    total_val += current_val
                    
                    pnl_str = f"+${pnl:.2f} (+{pnl_pct:.2f}%)" if pnl >= 0 else f"-${abs(pnl):.2f} ({pnl_pct:.2f}%)"
                    print(f"{sym:<22} | {opt_desc:<11} | {qty:<4.0f} | ${cost_basis:<9.2f} | ${opt_bid:<7.2f} | ${current_val:<10.2f} | {gex_status:<11} | {pnl_str}")

                total_pnl = total_val - total_cost
                total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
                tot_str = f"+${total_pnl:.2f} (+{total_pnl_pct:.2f}%)" if total_pnl >= 0 else f"-${abs(total_pnl):.2f} ({total_pnl_pct:.2f}%)"
                
                print("-" * 116)
                print(f"AGGREGATE PORTFOLIO SUMMARY | Total Invested: ${total_cost:.2f} | Current Value: ${total_val:.2f} | Total PnL: {tot_str}")
            else:
                print("No open positions active.")

        except Exception as e:
            print(f"[!] Polling error: {e}")

        time.sleep(interval)

if __name__ == "__main__":
    import sys
    target_env = sys.argv[1] if len(sys.argv) > 1 else "SANDBOX"
    poll_pnl_loop(target_env, interval=2.5)
