import os, sys, json, time, requests, boto3, sqlite3
from datetime import datetime
from dotenv import load_dotenv

if os.path.exists('.env.prod'):
    load_dotenv('.env.prod', override=True)
else:
    load_dotenv(override=True)

date_str = datetime.now().strftime('%Y-%m-%d')
token = os.getenv("TRADIER_PROD_TOKEN") or os.getenv("TRADIER_TOKEN")
headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
region = os.getenv("AWS_REGION", "us-east-1")

def get_closed_trades(target_env='ALL'):
    trades = []
    # 1. Primary: DynamoDB
    try:
        dynamodb = boto3.resource('dynamodb', region_name=region)
        table = dynamodb.Table('HarmonizedTrades')
        res = table.scan()
        for item in res.get('Items', []):
            st = str(item.get('exit_status', '')).upper()
            ts = str(item.get('exit_timestamp', item.get('timestamp', '')))
            env = str(item.get('execution_env', 'SANDBOX')).upper()
            if target_env != 'ALL' and env != target_env:
                continue
            if ('CLOSED' in st or '[SCJ]' in st) and (date_str in ts or not ts):
                trades.append(item)
    except Exception as e:
        print(f"[-] DynamoDB scan warning: {e}")

    # 2. Fallback: SQLite
    if not trades and os.path.exists("harm_telemetry.db"):
        try:
            conn = sqlite3.connect("harm_telemetry.db")
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            rows = c.execute("SELECT * FROM trades WHERE exit_status != 'ACTIVE'").fetchall()
            trades = [dict(r) for r in rows]
            conn.close()
        except Exception as e:
            print(f"[-] SQLite scan warning: {e}")

    return trades

def fetch_timesales(symbol, start_dt):
    url = "https://api.tradier.com/v1/markets/timesales"
    params = {
        "symbol": symbol,
        "interval": "1min",
        "start": f"{date_str} {start_dt}",
        "end": f"{date_str} 16:00",
        "session_filter": "all"
    }
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        if r.status_code == 200:
            bars = r.json().get("series", {}).get("data", [])
            return [bars] if isinstance(bars, dict) else bars
    except Exception as e:
        print(f"[-] Error fetching timesales for {symbol}: {e}")
    return []

def simulate_trade(occ_symbol, entry_px, actual_exit_px, shares, start_time):
    start_fmt = start_time.split(' ')[-1][:5] if ' ' in start_time else "09:30"
    bars = fetch_timesales(occ_symbol, start_fmt)
    if not bars:
        return None

    actual_pnl = round((actual_exit_px - entry_px) * 100 * shares, 2)
    peak_px = entry_px
    mttp_stop = round(entry_px * 0.80, 2)
    sim_exit = None

    for bar in bars:
        hi = float(bar.get("high") or 0.0)
        lo = float(bar.get("low") or 0.0)
        peak_px = max(peak_px, hi)
        peak_gain_pct = ((peak_px - entry_px) / entry_px) * 100.0

        if peak_gain_pct >= 35.0:
            calc_stop = round(peak_px * 0.90, 2)
        elif peak_gain_pct >= 20.0:
            calc_stop = round(max(entry_px * 1.10, peak_px * 0.88), 2)
        elif peak_gain_pct >= 10.0:
            calc_stop = round(entry_px, 2)
        elif peak_gain_pct >= 5.0:
            calc_stop = round(entry_px * 0.97, 2)
        else:
            calc_stop = round(entry_px * 0.80, 2)

        mttp_stop = max(mttp_stop, calc_stop)

        if not sim_exit and lo <= mttp_stop:
            sim_pnl = round((mttp_stop - entry_px) * 100 * shares, 2)
            sim_exit = {
                "exit_price": mttp_stop,
                "exit_time": bar.get("time"),
                "pnl": sim_pnl,
                "peak_seen": peak_px,
                "peak_theoretical_pnl": round((peak_px - entry_px) * 100 * shares, 2)
            }

    if not sim_exit and bars:
        last_cl = float(bars[-1].get("close") or entry_px)
        sim_exit = {
            "exit_price": last_cl,
            "exit_time": bars[-1].get("time"),
            "pnl": round((last_cl - entry_px) * 100 * shares, 2),
            "peak_seen": peak_px,
            "peak_theoretical_pnl": round((peak_px - entry_px) * 100 * shares, 2)
        }

    return {
        "actual_exit": actual_exit_px,
        "actual_pnl": actual_pnl,
        "mttp_sim": sim_exit,
        "alpha_diff": round((sim_exit["pnl"] - actual_pnl), 2) if sim_exit else 0.0
    }

def main():
    print(f"\n==========================================================================")
    print(f"  HARM.AI NIGHTLY CSO & MTTP REPLAY OPTIMIZER | {date_str}")
    print(f"==========================================================================")
    
    target_env = sys.argv[1].upper() if len(sys.argv) > 1 else "ALL"
    trades = get_closed_trades(target_env)
    print(f"[*] Target Filter: {target_env}")
    print(f"[*] Found {len(trades)} closed trades to analyze for {date_str}.\n")
    if not trades:
        return

    results = []
    tot_actual = 0.0
    tot_mttp = 0.0
    tot_peak = 0.0
    tot_alpha = 0.0

    print(f"{'SYMBOL':<22} | {'ENV':<7} | {'QTY':<4} | {'ACTUAL PNL':<12} | {'MTTP PNL':<12} | {'PEAK PNL':<12} | {'ALPHA GAIN':<12}")
    print("-" * 95)

    for t in trades:
        occ = t.get("occ_symbol") or t.get("ticker")
        if not occ or len(occ) < 10:
            continue

        try:
            entry_p = float(t.get("entry_price") or 0.0)
            exit_p = float(t.get("exit_price") or entry_p)
            shares = abs(int(float(t.get("shares", 1.0) or 1.0)))
            if shares == 0: shares = 2
            ts = str(t.get("timestamp") or "09:30:00")

            sim = simulate_trade(occ, entry_p, exit_p, shares, ts)
            if sim and sim["mttp_sim"]:
                m = sim["mttp_sim"]
                env_val = str(t.get('execution_env', 'SANDBOX')).upper()
                
                tot_actual += sim['actual_pnl']
                tot_mttp += m['pnl']
                tot_peak += m['peak_theoretical_pnl']
                tot_alpha += sim['alpha_diff']

                print(f"{occ:<22} | {env_val:<7} | {shares:<4} | ${sim['actual_pnl']:<11.2f} | ${m['pnl']:<11.2f} | ${m['peak_theoretical_pnl']:<11.2f} | ${sim['alpha_diff']:+11.2f}")
                results.append({
                    "trade_id": t.get("trade_id"),
                    "occ_symbol": occ,
                    "entry_price": entry_p,
                    "actual_exit": exit_p,
                    "actual_pnl": sim["actual_pnl"],
                    "mttp_exit": m["exit_price"],
                    "mttp_pnl": m["pnl"],
                    "peak_seen": m["peak_seen"],
                    "peak_pnl": m["peak_theoretical_pnl"],
                    "alpha_difference": sim["alpha_diff"]
                })
        except Exception as e:
            print(f"[-] Skipping {occ}: {e}")

    print("=" * 95)
    print(f"{'TOTAL PORTFOLIO LEDGER':<33} | ${tot_actual:<11.2f} | ${tot_mttp:<11.2f} | ${tot_peak:<11.2f} | ${tot_alpha:+11.2f}")
    print("=" * 95)

    # Save summary report locally
    os.makedirs("logs/nightly_replays", exist_ok=True)
    report_path = f"logs/nightly_replays/replay_{date_str}.json"
    with open(report_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[✓] Nightly optimization audit written to: {report_path}")

    # Upload report to S3
    try:
        s3 = boto3.client('s3', region_name=region)
        bucket = "harmonized-ai-telemetry-bucket"
        s3.upload_file(report_path, bucket, f"replays/replay_{date_str}.json")
        print(f"[✓] Replay audit uploaded to S3: s3://{bucket}/replays/replay_{date_str}.json")
    except Exception as e:
        print(f"[-] S3 replay upload note: {e}")

if __name__ == "__main__":
    main()
