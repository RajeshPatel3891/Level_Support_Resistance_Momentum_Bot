# ==============================================================================
# HARM.AI LIVE GSG GUARD & DYNAMODB PERSISTED RECOVERY PROTECTOR
# ==============================================================================
import os
import time
import json
import boto3
import requests
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv('AWS_REGION', 'us-east-1')

def get_tradier_token():
    token = os.getenv('TRADIER_ACCESS_TOKEN') or os.getenv('TRADIER_TOKEN') or os.getenv('TRADIER_SANDBOX_TOKEN')
    if token:
        return token
    if os.path.exists('system_config.json'):
        try:
            with open('system_config.json', 'r') as f:
                cfg = json.load(f)
                return cfg.get('tradier_access_token', cfg.get('TRADIER_ACCESS_TOKEN', ''))
        except Exception:
            pass
    return ''

TRADIER_TOKEN = get_tradier_token()
ACC_ID = os.getenv('TRADIER_ACCOUNT_ID')
dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table('HarmonizedTrades')

def fetch_tradier_quote(occ_symbol):
    """Fetches mark price, dynamically attempting Live and Sandbox endpoints."""
    if not TRADIER_TOKEN or not occ_symbol:
        return 0.0, "https://sandbox.tradier.com/v1"
    
    endpoints = [
        "https://api.tradier.com/v1/markets/quotes",
        "https://sandbox.tradier.com/v1/markets/quotes"
    ]
    headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
    
    for url in endpoints:
        try:
            r = requests.get(f"{url}?symbols={occ_symbol}", headers=headers, timeout=3)
            if r.status_code == 200:
                q = r.json().get('quotes', {}).get('quote', {})
                if isinstance(q, list):
                    q = q[0] if q else {}
                bid = float(q.get('bid') or 0.0)
                ask = float(q.get('ask') or 0.0)
                last = float(q.get('last') or 0.0)
                
                base_url = "https://api.tradier.com/v1" if "api.tradier" in url else "https://sandbox.tradier.com/v1"
                
                if ask > 0 and bid > 0:
                    return round((ask + bid) / 2.0, 2), base_url
                mark = ask if ask > 0 else (last if last > 0 else 0.0)
                return mark, base_url
            elif r.status_code == 401:
                continue
        except Exception:
            continue
            
    return 0.0, "https://sandbox.tradier.com/v1"

def execute_tradier_close(occ_symbol, quantity, base_url):
    """Submits an immediate sell_to_close market order to Tradier."""
    if not TRADIER_TOKEN or not ACC_ID:
        print("[!] Missing Tradier credentials for execution.")
        return False
        
    try:
        symbol_root = occ_symbol[:4].strip("0123456789 ")
        headers = {'Authorization': f'Bearer {TRADIER_TOKEN}', 'Accept': 'application/json'}
        payload = {
            "class": "option",
            "symbol": symbol_root,
            "option_symbol": occ_symbol,
            "side": "sell_to_close",
            "quantity": str(abs(int(float(quantity)))),
            "type": "market",
            "duration": "day"
        }
        res = requests.post(f"{base_url}/accounts/{ACC_ID}/orders", data=payload, headers=headers, timeout=5)
        if res.status_code == 200:
            print(f"  [✓ TRADIER CLOSE SUCCESS] Order submitted for {occ_symbol}")
            return True
        else:
            print(f"  [! TRADIER CLOSE FAILED] {res.status_code}: {res.text}")
            return False
    except Exception as e:
        print(f"  [! CLOSE EXCEPTION] {e}")
        return False

def run_live_gsg_guard():
    print("==========================================================")
    print("🛡️ LIVE DYNAMODB GSG GUARD & PERSISTED RECOVERY ACTIVE")
    print("==========================================================")

    while True:
        try:
            res = table.scan()
            items = [i for i in res.get('Items', []) if str(i.get('exit_status', '')).upper() == 'ACTIVE']

            if not items:
                print("[*] No active trades in DynamoDB. Sleeping 5s...")
                time.sleep(5)
                continue

            for item in items:
                tenant_id = item.get('tenant_id', 'COMPANY_A')
                trade_id = item.get('trade_id')
                ticker = str(item.get('ticker', '')).upper()
                occ_symbol = str(item.get('occ_symbol', ticker))
                entry_price = float(item.get('entry_price', 0.80) or 0.80)
                shares = float(item.get('shares', 1.0) or 1.0)

                # Fetch real-time live mark with endpoint auto-switching
                live_mark, active_base_url = fetch_tradier_quote(occ_symbol)
                if live_mark == 0.0:
                    live_mark = float(item.get('current_mark', entry_price) or entry_price)

                dollar_pnl = round((live_mark - entry_price) * 100.0 * shares, 2)
                pnl_pct = round(((live_mark - entry_price) / entry_price) * 100.0, 1) if entry_price > 0 else 0.0

                # ----------------------------------------------------------------------
                # DYNAMODB PERSISTENCE: Retrieve or persist min_pnl_seen in DynamoDB
                # ----------------------------------------------------------------------
                raw_min_seen = item.get('min_pnl_seen')
                if raw_min_seen is None:
                    min_seen = dollar_pnl
                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': trade_id},
                        UpdateExpression="SET min_pnl_seen = :m",
                        ExpressionAttributeValues={':m': str(min_seen)}
                    )
                else:
                    db_min_seen = float(raw_min_seen)
                    if dollar_pnl < db_min_seen:
                        min_seen = dollar_pnl
                        table.update_item(
                            Key={'tenant_id': tenant_id, 'trade_id': trade_id},
                            UpdateExpression="SET min_pnl_seen = :m",
                            ExpressionAttributeValues={':m': str(min_seen)}
                        )
                    else:
                        min_seen = db_min_seen

                print(f"[{ticker}] Mark: ${live_mark:.2f} | Entry: ${entry_price:.2f} | PnL: {'+' if dollar_pnl>=0 else ''}${dollar_pnl:.2f} ({pnl_pct}%) | Persisted Min: ${min_seen:+.2f}")

                # ----------------------------------------------------------------------
                # RULE 1: Red-to-Green Recovery Rule (Immediate Market Sell at >= +$1.00)
                # ----------------------------------------------------------------------
                if min_seen < 0.0 and dollar_pnl >= 1.00:
                    print(f"  [🛡️ GSG RECOVERY EXIT] {ticker} dipped red (${min_seen:.2f}) & recovered to green (${dollar_pnl:.2f}). EXECUTING MARKET CLOSE!")
                    if execute_tradier_close(occ_symbol, shares, active_base_url):
                        table.update_item(
                            Key={'tenant_id': tenant_id, 'trade_id': trade_id},
                            UpdateExpression="SET exit_status = :st, exit_price = :px, net_pnl = :pnl",
                            ExpressionAttributeValues={':st': 'GSG_RECOVERY_CLOSE', ':px': str(live_mark), ':pnl': str(dollar_pnl)}
                        )
                        continue

                # ----------------------------------------------------------------------
                # RULE 2: Standard GSG Profit Lock -> Ratchet stop & update dashboard badge
                # ----------------------------------------------------------------------
                if dollar_pnl >= 1.00:
                    new_sl = round(entry_price + 0.01, 2)
                    table.update_item(
                        Key={'tenant_id': tenant_id, 'trade_id': trade_id},
                        UpdateExpression="SET stop_loss = :sl, cso_status = :cso, cso_recommendation = :cso, current_mark = :mark",
                        ExpressionAttributeValues={':sl': str(new_sl), ':cso': 'TIGHTEN', ':mark': str(live_mark)}
                    )
                    print(f"  [🔒 GSG LOCK] {ticker} PnL is +${dollar_pnl:.2f} -> Stop raised to ${new_sl:.2f} (CSO: TIGHTEN)")

                # ----------------------------------------------------------------------
                # RULE 3: Hard Stop Exit Trigger
                # ----------------------------------------------------------------------
                current_sl = float(item.get('stop_loss', entry_price * 0.80) or (entry_price * 0.80))
                if live_mark <= current_sl and live_mark < entry_price:
                    print(f"  [🚨 GSG STOP TRIGGERED] {ticker} hit stop mark ${live_mark:.2f} <= ${current_sl:.2f}. EXECUTING MARKET CLOSE!")
                    if execute_tradier_close(occ_symbol, shares, active_base_url):
                        table.update_item(
                            Key={'tenant_id': tenant_id, 'trade_id': trade_id},
                            UpdateExpression="SET exit_status = :st, exit_price = :px, net_pnl = :pnl",
                            ExpressionAttributeValues={':st': 'GSG_STOP_EXIT', ':px': str(live_mark), ':pnl': str(dollar_pnl)}
                        )

        except KeyboardInterrupt:
            print("\n[*] GSG Guard manually stopped.")
            break
        except Exception as e:
            print(f"[!] Guard Loop Error: {e}")

        time.sleep(5)

if __name__ == '__main__':
    run_live_gsg_guard()
