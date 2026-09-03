import os, sys, time, boto3, requests
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr

env_file = '.env.prod' if os.path.exists('.env.prod') else '.env'
load_dotenv(env_file, override=False)

ENV = os.getenv("EXECUTION_ENV", "PRODUCTION")
ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "6YB87601")
TOKEN = os.getenv("TRADIER_PROD_TOKEN") or os.getenv("TRADIER_TOKEN")
BASE_URL = os.getenv("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip('/')
REGION = os.getenv("AWS_REGION", "us-east-1")
TABLE_NAME = os.getenv("DYNAMODB_TABLE", "HarmonizedTrades")

dynamodb = boto3.resource('dynamodb', region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

def get_quotes(symbols):
    if not symbols:
        return {}
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    try:
        res = requests.get(f"{BASE_URL}/markets/quotes", params={"symbols": ",".join(symbols)}, headers=headers, timeout=5)
        if res.status_code == 200:
            q_data = res.json().get("quotes", {}).get("quote", [])
            if isinstance(q_data, dict):
                q_data = [q_data]
            return {q.get("symbol"): float(q.get("last") or q.get("close") or 0.0) for q in q_data}
    except Exception:
        pass
    return {}

while True:
    os.system('clear')
    now = time.strftime('%Y-%m-%d %H:%M:%S ET')
    print("=" * 115)
    print(f"📊 LIVE PNL & POSITION MONITOR | {ENV} ({ACCOUNT_ID}) | {now}")
    print("=" * 115)
    print(f"{'SYMBOL':<22} | {'DIR':<4} | {'ENTRY':<7} | {'MARK':<7} | {'SHARES':<6} | {'STOP':<7} | {'STATUS':<10} | {'PNL'}")
    print("-" * 115)

    try:
        response = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        items = [i for i in response.get('Items', []) if str(i.get('shares', '0')) not in ['0', 'None']]
        
        symbols = [i.get('occ_symbol', i.get('ticker')) for i in items if i.get('occ_symbol', i.get('ticker'))]
        quotes = get_quotes(symbols)

        tot_pnl = 0.0
        for item in items:
            sym = item.get('occ_symbol', item.get('ticker'))
            direction = item.get('direction', 'PUT')
            entry = float(item.get('entry_price', 0.0))
            shares = int(item.get('shares', 1))
            stop = float(item.get('stop_loss', 0.0))
            status = item.get('exit_status', 'ACTIVE')
            mark = quotes.get(sym, entry)

            pnl_val = (mark - entry) * 100 * shares if direction == 'PUT' or direction == 'CALL' else 0.0
            pnl_pct = ((mark - entry) / entry * 100) if entry > 0 else 0.0
            tot_pnl += pnl_val

            sign = "+" if pnl_val >= 0 else ""
            print(f"{sym:<22} | {direction:<4} | ${entry:<6.2f} | ${mark:<6.2f} | {shares:<6} | ${stop:<6.2f} | {status:<10} | {sign}${pnl_val:.2f} ({sign}{pnl_pct:.1f}%)")

        print("=" * 115)
        print(f"💡 ACTIVE OPEN POSITIONS: {len(items)} | NET PORTFOLIO DELTA: {'+' if tot_pnl >= 0 else ''}${tot_pnl:.2f}")
        print("=" * 115)
    except Exception as e:
        print(f"[-] Error querying state: {e}")

    time.sleep(5)
