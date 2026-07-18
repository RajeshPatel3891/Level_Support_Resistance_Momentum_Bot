import sqlite3
import os
import json
import requests
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

def get_live_quote(symbol):
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        r = requests.get(f"https://sandbox.tradier.com/v1/markets/quotes?symbols={symbol}", headers=headers)
        if r.status_code == 200:
            quote = r.json().get('quotes', {}).get('quote', {})
            return quote[0] if isinstance(quote, list) else quote
    except:
        return {}
    return {}

def load_trading_levels():
    try:
        with open("trading_levels.json", "r") as f:
            return json.load(f)
    except:
        return {}

def audit_ecosystem():
    conn = sqlite3.connect("harm_telemetry.db")
    query = """
        SELECT ticker, spot_price, stop_loss, take_profit, exit_status, strategy, exit_price, net_pnl, timestamp
        FROM trades 
        WHERE id IN (SELECT MAX(id) FROM trades GROUP BY ticker)
    """
    db_records = conn.execute(query).fetchall()
    conn.close()
    
    levels_data = load_trading_levels()
    today_str = date.today().isoformat()
    
    active_rows = []
    exited_rows = []
    
    for row in db_records:
        ticker, basis, sl, tp, status, strategy, exit_price, net_pnl, ts = row
        display_status = status if status else "ACTIVE"
        
        is_today = True
        if ts and today_str not in ts:
            is_today = False
            
        if display_status in ['ACTIVE', 'SIM_TRAILING_STOP'] and is_today:
            active_rows.append((ticker, basis, sl, tp, display_status, strategy))
        elif is_today:
            exited_rows.append((ticker, basis, sl, tp, display_status, exit_price, net_pnl))

    print("=" * 160)
    print("🦅 HARM.AI // UNIFIED REAL-TIME ACTIVE MONITORING MATRIX")
    print("=" * 160)
    print(f"{'Asset':<6} | {'DB Status':<10} | {'Live Price':<10} | {'Basis':<8} | {'P&L %':<7} | {'True P&L':<10} | {'Exit Target (TP)':<18} | {'G1 Momentum Filter':<24} | {'G2 Velocity Filter':<24} | {'Execution Verdict'}")
    print("-" * 160)
    
    total_dollar_pnl = 0.0
    
    for row in active_rows:
        ticker, basis, sl, tp, display_status, strategy = row
        quote = get_live_quote(ticker)
        last_price = float(quote.get('last', 0)) if quote.get('last') else basis
        
        pnl_pct = ((last_price - basis) / basis) * 100 if basis > 0 else 0
        risk_dist = abs(basis - sl)
        
        if risk_dist > 0:
            shares = 85.0 / risk_dist
            dollar_pnl = (last_price - basis) * shares
            if last_price <= sl:
                dollar_pnl = -85.00
        else:
            dollar_pnl = 0.0
            
        total_dollar_pnl += dollar_pnl
        
        asset_levels = levels_data.get(ticker, {})
        vwap = asset_levels.get('vwap', basis * 0.99)
        sa = asset_levels.get('support_a', sl * 1.002)
        sb = asset_levels.get('support_b', basis * 1.002)
        ra = asset_levels.get('resistance_a', basis * 0.998)
        rb = asset_levels.get('resistance_b', tp * 0.998)
        
        is_at_support = (sa <= last_price <= sb)
        is_at_resistance = (ra <= last_price <= rb)
        
        if is_at_support:
            g1_passed = (last_price >= vwap)
            g1_status = "✅ PASSED (Above VWAP)" if g1_passed else "❌ BLOCKED (Below VWAP)"
        elif is_at_resistance:
            g1_passed = (last_price < vwap)
            g1_status = "✅ PASSED (Below VWAP)" if g1_passed else "❌ BLOCKED (Above VWAP)"
        else:
            g1_passed = False
            g1_status = "❌ BLOCKED (No Active Zone)"
            
        is_freefall = (vwap - last_price) > (0.15 * vwap)
        g2_status = "❌ ENGAGED (Freefall)" if is_freefall else "✅ CLEAN (No Waterfall)"
        g2_passed = not is_freefall
        
        if (is_at_support or is_at_resistance) and g1_passed and g2_passed:
            exec_verdict = "ARMED (Route Open)"
        elif not (is_at_support or is_at_resistance):
            exec_verdict = "OUT_OF_BOUNDS"
        else:
            exec_verdict = "GUARDRAIL_BLOCKED"
            
        tp_str = f"${tp:.2f}" if tp else "-"
        print(f"{ticker:<6} | {display_status:<10} | ${last_price:<9.2f} | ${basis:<7.2f} | {pnl_pct:>+6.2f}% | ${dollar_pnl:>+8.2f} | {tp_str:<18} | {g1_status:<24} | {g2_status:<24} | {exec_verdict}")
        
    print("=" * 160)
    print(f"💰 AGGREGATE OPEN FLOATING PORTFOLIO P&L:  ${total_dollar_pnl:+,.2f}")
    print("=" * 160)
    print("\n")

    print("=" * 160)
    print("🦅 HARM.AI // DAILY EXITED DISPOSITION PROFILE (CLOSED TRANSACTIONS)")
    print("=" * 160)
    print(f"{'Asset':<8} | {'Disposition':<15} | {'Entry Basis':<12} | {'Exit Realized':<15} | {'Realized P&L'}")
    print("-" * 160)
    
    if not exited_rows:
        print(f"{' ':^70}No realized exits recorded on today's operating cycle.")
    else:
        for row in exited_rows:
            ticker, basis, sl, tp, status, ep, pnl = row
            ep_str = f"${ep:.2f}" if ep else "-"
            pnl_str = f"${pnl:+.2f}" if pnl is not None else "-$85.00 (Hard Risk Ceiling)"
            print(f"{ticker:<8} | {status:<15} | ${basis:<11.2f} | {ep_str:<15} | {pnl_str}")
    print("=" * 160)
    print("\n")

    print("=" * 160)
    print("🦅 HARM.AI // PIPELINE INTAKE QUEUE WATCHLIST (POTENTIAL NEXT TRADES)")
    print("=" * 160)
    print(f"{'Asset':<8} | {'Live Price':<10} | {'Tracked Target Range':<30} | {'Distance to Entry Range'}")
    print("-" * 160)
    
    scan_count = 0
    for sym, lvls in levels_data.items():
        if sym not in [r[0] for r in active_rows]:
            sa = lvls.get("support_a", 0)
            sb = lvls.get("support_b", 0)
            if sa > 0 and sb > 0:
                scan_count += 1
                q = get_live_quote(sym)
                lp = float(q.get('last', 0)) if q.get('last') else (sa + sb) / 2
                
                mid_point = (sa + sb) / 2
                dist = lp - mid_point
                dist_pct = (dist / lp) * 100 if lp > 0 else 0
                
                range_str = f"${sa:.2f} - ${sb:.2f}"
                if sa <= lp <= sb:
                    proximity = "⚡ INSIDE ENTRY RANGE"
                else:
                    proximity = f"{dist_pct:>+6.2f}% clear of pool"
                    
                print(f"{sym:<8} | ${lp:<9.2f} | {range_str:<30} | {proximity}")
                
    if scan_count == 0:
        print(f"{' ':^70}No valid structural levels matching candidate profiles inside trading_levels.json")
    print("=" * 160)

if __name__ == "__main__":
    audit_ecosystem()
