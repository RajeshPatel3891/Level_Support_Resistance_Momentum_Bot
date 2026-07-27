import re
import json

new_func = '''@app.get("/api/proximity")
async def get_proximity():
    proximity_data = {}
    
    # 1. Load default watchlist matrix levels from local json state
    try:
        if os.path.exists('trading_levels.json'):
            with open('trading_levels.json', 'r') as f:
                levels_file = json.load(f)
                
            for ticker, info in levels_file.items():
                spot = float(info.get('spot', info.get('last_price', 0.0)))
                vwap = float(info.get('vwap', spot))
                armed = bool(info.get('execution_armed', False)) or str(info.get('status', '')).upper() == 'ARMED'
                
                res_a = info.get('resistance_a', info.get('resistance', [0])[0] if isinstance(info.get('resistance'), list) else 0)
                gap_val = abs(spot - float(res_a)) if res_a else 0.0
                gap_pct_val = (gap_val / spot * 100) if spot > 0 else 0.0
                
                proximity_data[ticker] = {
                    'armed': armed,
                    'spot': spot,
                    'vwap': vwap,
                    'target': f"{res_a:.2f}" if isinstance(res_a, (int, float)) else str(res_a),
                    'gap_dollars': f"${gap_val:.2f}",
                    'gap_pct': f"{gap_pct_val:.2f}%"
                }
    except Exception as e:
        print(f"Error reading trading_levels.json: {e}")

    # 2. Overlay live active trades from DynamoDB state if present
    try:
        active_trades, *_ = fetch_portfolio_state()
        for trade in active_trades:
            ticker = trade.get('ticker')
            if ticker:
                spot = float(trade.get('spot_price', trade.get('price', 0)))
                armed = str(trade.get('cso_recommendation', '')).upper() == 'ARMED'
                
                gex_dist = str(trade.get('gex_dist', '0.00 (0.0%)'))
                parts = gex_dist.split(' ')
                gap_dollars = f"${parts[0]}" if len(parts) > 0 else "$0.00"
                gap_pct = parts[1].replace('(', '').replace(')', '') if len(parts) > 1 else '0.0%'
                
                proximity_data[ticker] = {
                    'armed': armed,
                    'spot': spot,
                    'vwap': float(trade.get('entry_price', spot)),
                    'target': str(trade.get('gex_target_str', trade.get('take_profit', 'N/A'))),
                    'gap_dollars': gap_dollars,
                    'gap_pct': gap_pct
                }
    except Exception as e:
        print(f"Error fetching portfolio active overlay: {e}")

    return proximity_data'''

with open('dashboard_server.py', 'r') as f:
    content = f.read()

pattern = r'@app\.get\("/api/proximity"\).*?(?=@app\.get)'
if re.search(pattern, content, re.DOTALL):
    content = re.sub(pattern, new_func + '\n\n', content, flags=re.DOTALL)
    with open('dashboard_server.py', 'w') as f:
        f.write(content)
    print('[✓] Route updated to load all tickers from trading_levels.json!')
else:
    print('[!] Could not match proximity function pattern.')
