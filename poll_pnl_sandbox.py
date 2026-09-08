import os, sys, time, boto3, requests
from dotenv import load_dotenv

load_dotenv('.env', override=False)

ENV = "SANDBOX"
ACCOUNT_ID = os.getenv("TRADIER_ACCOUNT_ID", "VA83416608")
TOKEN = os.getenv("TRADIER_SANDBOX_TOKEN") or os.getenv("TRADIER_TOKEN")
BASE_URL = "https://sandbox.tradier.com/v1"
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
            quote_map = {}
            for q in q_data:
                sym = q.get("symbol")
                bid = float(q.get("bid") or 0.0)
                ask = float(q.get("ask") or 0.0)
                last = float(q.get("last") or q.get("close") or 0.0)
                if bid > 0 and ask > 0:
                    quote_map[sym] = round((bid + ask) / 2.0, 2)
                else:
                    quote_map[sym] = last if last > 0 else ask
            return quote_map
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
        raw_items = []
        done = False
        start_key = None
        while not done:
            kwargs = {}
            if start_key:
                kwargs['ExclusiveStartKey'] = start_key
            res = table.scan(**kwargs)
            raw_items.extend(res.get('Items', []))
            start_key = res.get('LastEvaluatedKey')
            done = start_key is None
        
        items = []
        for i in raw_items:
            status = str(i.get('exit_status', '')).strip().upper()
            shares = str(i.get('shares', '0')).strip()
            env_val = str(i.get('execution_env', '')).strip().upper()
            is_live = int(i.get('is_live', 1))
            
            if status == 'ACTIVE' and shares not in ['0', 'None', '0.0', '']:
                if env_val == 'SANDBOX' or is_live == 0:
                    items.append(i)

        symbols = [i.get('occ_symbol', i.get('ticker')) for i in items if i.get('occ_symbol', i.get('ticker'))]
        quotes = get_quotes(symbols)

        tot_pnl = 0.0
        for item in items:
            sym = item.get('occ_symbol', item.get('ticker'))
            direction = str(item.get('direction', 'CALL')).upper()
            entry = float(item.get('entry_price', 0.0))
            try:
                shares = int(float(item.get('shares', 1)))
            except Exception:
                shares = 1
            stop = float(item.get('stop_loss', 0.0))
            status = item.get('exit_status', 'ACTIVE')
            mark = quotes.get(sym, entry)

            if direction == 'PUT':
                pnl_val = (entry - mark) * 100 * shares
                pnl_pct = ((entry - mark) / entry * 100) if entry > 0 else 0.0
            else:
                pnl_val = (mark - entry) * 100 * shares
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
