import os, time, requests, json, sys

env = sys.argv[1] if len(sys.argv) > 1 else 'SANDBOX'
acct = '6YB87601' if env == 'PROD' else 'VA83416608'
token = 'fyR75AACwlIYhkMyev1doRh6gnSr' if env == 'PROD' else 'hcY1t0sY8RZmcsfVjQCA41ecAkFT'
base_url = 'https://api.tradier.com/v1' if env == 'PROD' else 'https://sandbox.tradier.com/v1'
headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

while True:
    try:
        os.system('clear')
        ts = time.strftime('%Y-%m-%d %H:%M:%S ET')
        print('='*110)
        print(f'📊 FARGATE IN-CONTAINER LIVE PNL & GEX MONITOR | {env} ({acct}) | {ts}')
        print('='*110)

        # Query internal container GEX state on localhost:8080
        gex_data = {}
        try:
            gex_data = requests.get('http://localhost:8080/api/proximity', timeout=1).json()
        except Exception:
            pass

        # Query Tradier Open Positions
        pos_res = requests.get(f'{base_url}/accounts/{acct}/positions', headers=headers, timeout=2).json()
        positions = pos_res.get('positions')
        positions = positions.get('position', []) if (positions and positions != 'null') else []
        if isinstance(positions, dict): positions = [positions]

        if positions:
            symbols = ','.join([p.get('symbol') for p in positions if p.get('symbol')])
            underlying_syms = list(set([s[:4].strip() for s in symbols.split(',')]))
            all_syms = symbols + ',' + ','.join(underlying_syms)

            quotes_dict = {}
            try:
                q_res = requests.get(f'{base_url}/markets/quotes', params={'symbols': all_syms}, headers=headers, timeout=2).json()
                quotes = q_res.get('quotes', {}).get('quote', [])
                if isinstance(quotes, dict): quotes = [quotes]
                for q in quotes:
                    quotes_dict[q.get('symbol')] = {'last': q.get('last', 0), 'bid': q.get('bid', 0)}
            except Exception:
                pass

            total_cost, total_val = 0, 0
            print(f"{'SYMBOL':<22} | {'QTY':<4} | {'COST BASIS':<10} | {'BID/LAST':<8} | {'MARKET VAL':<10} | {'GEX EXIT':<11} | {'LIVE PNL'}")
            print('-'*110)

            for p in positions:
                sym = p.get('symbol')
                underlying = sym[:4].strip()
                qty = float(p.get('quantity', 0))
                cost = float(p.get('cost_basis', 0))
                bid = quotes_dict.get(sym, {}).get('bid', 0)
                spot = quotes_dict.get(underlying, {}).get('last', 0)

                val = bid * qty * 100 if bid > 0 else cost
                pnl = val - cost
                pnl_pct = (pnl / cost * 100) if cost > 0 else 0
                total_cost += cost
                total_val += val

                gex_info = gex_data.get(underlying, {})
                call_tgt = float(gex_info.get('call_target', 0) or gex_info.get('target', 0))
                put_tgt = float(gex_info.get('put_target', 0))
                
                gex_status = 'WAITING'
                if call_tgt > 0 and spot >= call_tgt: gex_status = '🔥 ENGAGED'
                elif call_tgt > 0 and spot >= (call_tgt * 0.995): gex_status = '⚡ ARMED'
                elif put_tgt > 0 and spot <= put_tgt: gex_status = '🔥 ENGAGED'
                elif put_tgt > 0 and spot <= (put_tgt * 1.005): gex_status = '⚡ ARMED'

                pnl_str = f'+${pnl:.2f} (+{pnl_pct:.2f}%)' if pnl >= 0 else f'-${abs(pnl):.2f} ({pnl_pct:.2f}%)'
                print(f"{sym:<22} | {qty:<4.0f} | ${cost:<9.2f} | ${bid:<7.2f} | ${val:<10.2f} | {gex_status:<11} | {pnl_str}")

            tot_pnl = total_val - total_cost
            tot_pct = (tot_pnl / total_cost * 100) if total_cost > 0 else 0
            tot_str = f'+${tot_pnl:.2f} (+{tot_pct:.2f}%)' if tot_pnl >= 0 else f'-${abs(tot_pnl):.2f} ({tot_pct:.2f}%)'
            print('-'*110)
            print(f'AGGREGATE SUMMARY | Invested: ${total_cost:.2f} | Current Val: ${total_val:.2f} | PnL: {tot_str}')
        else:
            print('No open positions active.')

    except Exception as e:
        print(f'[!] Error: {e}')

    time.sleep(2.5)
