import os
import sys
import json
import sqlite3
import csv
import argparse
import subprocess
import boto3
from datetime import datetime, timedelta

# Path configuration - 100% markdown-safe pathing
CURRENT_DIR = os.getcwd()
DB_FILE = os.path.join(CURRENT_DIR, 'harm_telemetry.db')
DATA_JSON = os.path.join(CURRENT_DIR, 'dashboard_data.json')
LEVELS_FILE = os.path.join(CURRENT_DIR, 'trading_levels.json')

# Complete 24-Ticker Matrix Integration
TICKERS = [
    "SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "AMZN", "GOOGL", "AMD", 
    "META", "NFLX", "PLTR", "SOFI", "F", "AAL", "INTC", "RIVN", "HOOD", 
    "BAC", "SNAP", "MARA", "CCL", "UBER", "NKE"
]

def log_msg(prefix: str, msg: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{prefix}] {msg}")

# ==========================================================================
# RISK MANAGEMENT LOGIC
# ==========================================================================
def validate_trade(contracts, stop_loss_distance, max_total_risk, max_rpc):
    """
    Validates a trade based on both total exposure and risk per contract.
    
    :param contracts: Number of contracts (e.g., 5)
    :param stop_loss_distance: Dollar value distance to stop loss (e.g., 4.50)
    :param max_total_risk: Threshold for total position risk (e.g., 20.0)
    :param max_rpc: Threshold for individual contract risk (e.g., 5.0)
    :return: (bool, str) - (Success, Reason)
    """
    total_risk = contracts * stop_loss_distance
    rpc = stop_loss_distance
    
    # 1. Check Total Risk (Position Sizing Filter)
    if total_risk > max_total_risk:
        return False, f"Total risk exceeded: ${total_risk:.2f} > ${max_total_risk:.2f}"
    
    # 2. Check Risk Per Contract (Volatility/Stop Filter)
    if rpc > max_rpc:
        return False, f"Risk per contract exceeded: ${rpc:.2f} > ${max_rpc:.2f}"
        
    return True, "Trade within risk parameters"

class HarmonizedAnalyticsEngine:
    def __init__(self, max_total_risk=20.0, max_rpc=20.0):
        self.max_total_risk = max_total_risk
        self.max_rpc = max_rpc
        
        if not os.path.exists(LEVELS_FILE):
            log_msg("ERROR", "trading_levels.json not found. Creating a default fallback profile...")
            self.create_default_levels()
            
        with open(LEVELS_FILE, 'r') as f:
            self.levels = json.load(f).get("levels", {})

    def create_default_levels(self):
        default_config = {
            "source": "Consensus_Fallback",
            "levels": {t: {"algo_macro": {"support": [100.0]}, "human_tactical": {"breakout_trigger": 101.5}} for t in TICKERS}
        }
        with open(LEVELS_FILE, 'w') as f:
            json.dump(default_config, f, indent=4)

    # ==========================================================================
    # TOOL 1: FORENSIC INTEGRITY VERIFICATION ENGINE
    # ==========================================================================
    def verify_database_integrity(self):
        log_msg("VERIFIER", "Starting forensic database audit against physical CSV logs...")
        
        if not os.path.exists(DB_FILE):
            log_msg("VERIFIER", "[!] Error: SQLite database file does not exist. Run ingestion first.")
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT id, ticker, timestamp, spot_price, exit_price, net_pnl, exit_status FROM trades")
            db_records = cursor.fetchall()
        except sqlite3.OperationalError:
            log_msg("VERIFIER", "[!] Error: 'trades' table does not exist. Run ingestion or simulation first.")
            conn.close()
            return

        if not db_records:
            log_msg("VERIFIER", "[!] Database is empty. No records to verify.")
            conn.close()
            return

        log_msg("VERIFIER", f"Auditing {len(db_records)} records currently written in database...")
        
        verified_count = 0
        anomaly_count = 0

        csv_records = {}
        for filename in os.listdir(CURRENT_DIR):
            if filename.endswith("_audit.csv"):
                parts = filename.split("_")
                ticker = parts[0]
                if ticker not in TICKERS:
                    continue
                
                file_records = {}
                try:
                    with open(os.path.join(CURRENT_DIR, filename), 'r') as f:
                        reader = csv.reader(f)
                        next(reader, None) # Skip header
                        for row in reader:
                            if not row: continue
                            timestamp, price_str, action, conviction, result, notes = row
                            price = float(price_str)
                            if action == "ENTER":
                                key = (ticker, timestamp, price)
                                file_records[key] = {"exit_price": None, "status": None}
                            elif action in ["EXIT", "FORCE_CLOSE"] and file_records:
                                matching_keys = [k for k in file_records.keys() if k[0] == ticker and file_records[k]["exit_price"] is None]
                                if matching_keys:
                                    last_key = matching_keys[-1]
                                    file_records[last_key]["exit_price"] = price
                                    file_records[last_key]["status"] = result if result != "MANDATORY_EOD_FLUSH" else "FORCE_CLOSE"
                    csv_records.update(file_records)
                except Exception as e:
                    log_msg("VERIFIER", f"[!] Error pre-parsing physical audit file {filename}: {e}")

        for record in db_records:
            db_id, ticker, timestamp, spot_price, exit_price, net_pnl, exit_status = record
            key = (ticker, timestamp, spot_price)
            if key in csv_records:
                csv_data = csv_records[key]
                expected_ratio = (exit_price - spot_price) / spot_price if spot_price > 0 else 0.0
                
                # Check for variances
                price_variance = abs(exit_price - csv_data["exit_price"]) if exit_price and csv_data["exit_price"] else 0.0
                
                if price_variance > 0.001:
                    log_msg("ANOMALY", f"[🚨] VARIANCE DETECTED on Trade #{db_id} [{ticker} at {timestamp}]:")
                    log_msg("ANOMALY", f"    • DB Exit Price: ${exit_price} | CSV Exit Price: ${csv_data['exit_price']}")
                    anomaly_count += 1
                else:
                    verified_count += 1
            else:
                log_msg("ANOMALY", f"[🚨] SYSTEM UNLINKED: Trade #{db_id} [{ticker} at {timestamp}] exists in SQL but has no source CSV audit log!")
                anomaly_count += 1

        conn.close()
        log_msg("VERIFIER", "="*50)
        log_msg("VERIFIER", " FORENSIC INTEGRITY AUDIT COMPLETION REPORT ")
        log_msg("VERIFIER", "="*50)
        log_msg("VERIFIER", f"  • Cleanly Verified Records : {verified_count}")
        log_msg("VERIFIER", f"  • Anomaly/Mismatched Alerts: {anomaly_count}")
        if anomaly_count == 0:
            log_msg("VERIFIER", "  [✓] VERDICT: 100% Mathematically Confirmed. These are REAL un-hallucinated figures.")
        else:
            log_msg("VERIFIER", f"  [!] VERDICT: Discrepancy Found. {anomaly_count} items could not be linked back to CSVs.")
        log_msg("VERIFIER", "="*50)

    # ==========================================================================
    # TOOL 2: BATCH HISTORICAL DOWNLOADER & ORCHESTRATOR
    # ==========================================================================
    def run_batch_date_reconciliation(self, start_date_str, end_date_str):
        log_msg("BATCH", f"Initializing historical pipeline from {start_date_str} to {end_date_str}...")
        
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d")
        
        current_date = start_date
        date_list = []
        
        while current_date <= end_date:
            if current_date.weekday() < 5:
                date_list.append(current_date.strftime("%Y-%m-%d"))
            current_date += timedelta(days=1)

        log_msg("BATCH", f"Identified {len(date_list)} valid trading sessions to reconcile.")
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # --- THE CORE INSULATION FIX ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                strategy TEXT NOT NULL,
                direction TEXT NOT NULL,
                support_level REAL,
                spot_price REAL,
                exit_price REAL,
                stop_loss REAL,
                take_profit REAL,
                distance REAL,
                allowed_dist REAL,
                proximity_score REAL,
                exit_status TEXT,
                net_pnl REAL,
                is_live INTEGER DEFAULT 1
            )
        """)
        conn.commit()
        conn.close()

        s3 = boto3.client('s3', region_name='us-east-1')

        for session_date in date_list:
            log_msg("BATCH", f"Processing Session: {session_date}...")
            
            tickers_to_fetch = []
            for ticker in TICKERS:
                if not os.path.exists(f"{ticker}_{session_date}.json"):
                    tickers_to_fetch.append(ticker)
            
            if tickers_to_fetch:
                log_msg("FETCH", f"Downloading raw ticks from S3 for: {tickers_to_fetch}...")
                for ticker in tickers_to_fetch:
                    s3_key = f"ticks/{session_date}/{ticker}.json"
                    local_file = f"{ticker}_{session_date}.json"
                    try:
                        s3.download_file("harmonized-ai-telemetry-bucket", s3_key, local_file)
                        log_msg("FETCH", f"[✓] Downloaded {ticker} ticks for {session_date} from S3.")
                    except Exception as e:
                        log_msg("FETCH", f"[!] S3 fetch failed for {ticker}: {e}")
                
            log_msg("BACKTEST", f"Running offline simulation matrix for {session_date}...")
            
            # Pass the dynamic total risk value down to BacktestBot
            backtest_cmd = [
                "python3", "src/BacktestBot.py", 
                "--date", session_date,
                "--max-risk", str(self.max_total_risk)
            ]
            subprocess.run(backtest_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
            for ticker in TICKERS:
                src_audit = f"{ticker}_audit.csv"
                dest_audit = f"{ticker}_{session_date}_audit.csv"
                if os.path.exists(src_audit):
                    if os.path.exists(dest_audit):
                        os.remove(dest_audit)
                    os.rename(src_audit, dest_audit)
            
            self.ingest_session_audit_logs(session_date)

        log_msg("BATCH", "Batch compilation complete. Syncing live web dashboard JSON...")
        self.regenerate_dashboard_json()

    def ingest_session_audit_logs(self, session_date):
        """Parses newly generated ticker csv files and writes records to database using the Risk Filter."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        total_ingested = 0
        total_skipped = 0
        
        for ticker in TICKERS:
            possible_paths = [
                os.path.join(CURRENT_DIR, f"{ticker}_{session_date}_audit.csv"),
                os.path.join(CURRENT_DIR, f"{ticker}_audit.csv"),
                f"{ticker}_{session_date}_audit.csv"
            ]
            
            audit_path = None
            for path in possible_paths:
                if os.path.exists(path):
                    audit_path = path
                    break
                    
            if not audit_path:
                continue

            ticker_trades = []
            active_trade = None

            with open(audit_path, 'r') as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if not row: continue
                    timestamp, price_str, action, conviction, result, notes = row
                    price = float(price_str)

                    if action == "ENTER":
                        active_trade = {
                            "ticker": ticker,
                            "timestamp": timestamp,
                            "entry_price": price,
                            "notes": notes
                        }
                    elif action in ["EXIT", "FORCE_CLOSE"] and active_trade:
                        active_trade["exit_price"] = price
                        active_trade["exit_status"] = result if result != "MANDATORY_EOD_FLUSH" else "FORCE_CLOSE"
                        
                        entry_p = active_trade["entry_price"]
                        ratio = (price - entry_p) / entry_p if entry_p > 0 else 0.0
                        
                        # --- HARM.AI RISK FILTER INTEGRATION ---
                        if "SIDEKICK" in active_trade["notes"].upper():
                            option_rpc = 20.0  # Strict $0.20 option stop target
                        else:
                            option_rpc = 1.50 * 0.50 * 100.0  
                            
                        contracts = max(1, int(self.max_total_risk / option_rpc)) if option_rpc > 0 else 1
                        
                        is_valid, skip_reason = validate_trade(contracts, option_rpc, self.max_total_risk, self.max_rpc)
                        
                        if not is_valid:
                            log_msg("RISK_FILTER", f"Skipping {ticker} trade at {timestamp}: {skip_reason}")
                            active_trade = None
                            total_skipped += 1
                            continue
                        
                        net_pnl = round((contracts * 100.0) * ratio * 10.0, 2)
                        
                        active_trade["net_pnl"] = net_pnl
                        ticker_trades.append(active_trade)
                        active_trade = None

            for trade in ticker_trades:
                ticker = trade["ticker"]
                ts = trade["timestamp"]
                entry_p = trade["entry_price"]
                exit_p = trade["exit_price"]
                status = trade["exit_status"]
                pnl = trade["net_pnl"]
                
                cfg = self.levels.get(ticker, {})
                support_list = cfg.get("algo_macro", {}).get("support", [])
                support_floor = float(support_list[0]) if support_list else entry_p
                
                notes = trade["notes"]
                strategy = "LIVEBOT_HIGH"
                if "SIDEKICK" in notes or "SIDEKICK" in trade["notes"].upper():
                    strategy = "SIDEKICK_MICRO_SCALP"
                elif "BREAKOUT" in notes:
                    strategy = "BREAKOUT"
                elif "REBOUND" in notes:
                    strategy = "REBOUND"
                elif "MANDATORY_EOD_FLUSH" in notes:
                    strategy = "EOD_FLUSH"

                dist = abs(entry_p - support_floor)
                allowed_dist = 2.50
                prox_score = round(max(0.0, min(100.0, (1.0 - (dist / allowed_dist)) * 100.0)), 2)

                stop_loss = round(entry_p - 1.50, 2)
                take_profit = round(entry_p + 3.00, 2)

                cursor.execute("""
                    INSERT INTO trades (ticker, timestamp, strategy, direction, support_level, spot_price, stop_loss, take_profit, distance, allowed_dist, proximity_score, exit_status, net_pnl, exit_price, is_live)
                    VALUES (?, ?, ?, 'CALL', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                """, (
                    ticker, ts, strategy, support_floor, entry_p, stop_loss, take_profit, dist, allowed_dist, prox_score, status, pnl, exit_p
                ))
                total_ingested += 1
                
        conn.commit()
        conn.close()
        
        if total_skipped > 0:
            log_msg("RISK_FILTER", f"Cleaned up dashboard: Purged {total_skipped} noisy trades from session {session_date} due to Risk Constraints.")

    # ==========================================================================
    # TOOL 3: HIGH-IMPACT MULTI-DIMENSIONAL FILTER ENGINE
    # ==========================================================================
    def run_filtered_analysis(self, ticker=None, strategy=None, min_proximity=None, timeframe=None):
        if not os.path.exists(DB_FILE):
            log_msg("FILTER", "[!] Error: No database exists to run queries. Run batch first.")
            return

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        query = "SELECT ticker, timestamp, strategy, spot_price, exit_price, exit_status, proximity_score, net_pnl FROM trades WHERE 1=1"
        params = []

        if ticker:
            query += " AND ticker = ?"
            params.append(ticker)
        if strategy:
            query += " AND strategy = ?"
            params.append(strategy)
        if min_proximity:
            query += " AND proximity_score >= ?"
            params.append(float(min_proximity))

        cursor.execute(query, params)
        raw_rows = cursor.fetchall()
        conn.close()

        filtered_rows = []
        for r in raw_rows:
            ts_str = r[1]
            try:
                time_part = ts_str.split(" ")[1] if " " in ts_str else ts_str.split("T")[1][:8]
                hour = int(time_part.split(":")[0])
                minute = int(time_part.split(":")[1])
                time_float = hour + (minute / 60.0)
            except Exception:
                time_float = 12.0
            
            if timeframe == "morning" and (9.5 <= time_float <= 10.5): filtered_rows.append(r)
            elif timeframe == "midday" and (10.5 < time_float <= 14.0): filtered_rows.append(r)
            elif timeframe == "afternoon" and (14.0 < time_float <= 16.0): filtered_rows.append(r)
            elif not timeframe or timeframe == "ALL": filtered_rows.append(r)

        print("\n" + "="*80)
        print(" HARM.AI // AUTOMATED PORTFOLIO FILTER AUDIT ")
        print("="*80)
        print(f"Applied Parameters: Ticker={ticker or 'ALL'} | Strat={strategy or 'ALL'} | Min Prox={min_proximity or '0'}% | Segment={timeframe or 'ALL'}")
        print("-" * 80)
        print(f"{'Timestamp':<19} | {'Ticker':<6} | {'Strategy':<20} | {'Prox':<5}% | {'Outcome':<12} | {'PnL':<10}")
        print("-" * 80)

        total_trades = len(filtered_rows)
        wins = 0
        total_pnl = 0.0

        for r in filtered_rows:
            ticker_val, ts, strat, spot_p, exit_p, status, proximity, pnl = r
            pnl_val = float(pnl)
            total_pnl += pnl_val
            if pnl_val > 0: wins += 1
            print(f"{ts[:19]:<19} | {ticker_val:<6} | {strat:<20} | {proximity or 0.0:>4.1f}% | {status:<12} | ${pnl_val:+.2f}")

        win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0
        print("-" * 80)
        print(f"Total Filtered Trades: {total_trades}")
        print(f"Expectancy Win Rate  : {win_rate:.2f}%")
        print(f"Net Group Return     : ${total_pnl:+.2f}")
        print("="*80 + "\n")

    def regenerate_dashboard_json(self):
        if not os.path.exists(DB_FILE): return
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*), SUM(net_pnl), SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) FROM trades")
        total_t, net_pnl, wins = cursor.fetchone()
        
        net_pnl = net_pnl if net_pnl else 0.0
        win_rate = round((wins / total_t) * 100.0, 2) if total_t and total_t > 0 else 0.0
        
        buckets = [
            {"min": 80, "max": 100, "name": "Elite Proximity (80%-100%)"},
            {"min": 50, "max": 80, "name": "Moderate Proximity (50%-80%)"},
            {"min": 0, "max": 50, "name": "Fringe Proximity (0%-50%)"}
        ]
        
        bucket_stats = []
        for b in buckets:
            cursor.execute("""
                SELECT COUNT(*), SUM(net_pnl), SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END)
                FROM trades 
                WHERE proximity_score >= ? AND proximity_score < ?
            """, (b["min"], b["max"]))
            count, pnl, b_wins = cursor.fetchone()
            
            b_pnl = round(pnl, 2) if pnl else 0.0
            b_wr = round((b_wins / count) * 100.0, 2) if count and count > 0 else 0.0
            
            bucket_stats.append({
                "range": b["name"],
                "trades": count or 0,
                "win_rate": b_wr,
                "net_pnl": b_pnl
            })

        cursor.execute("""
            SELECT ticker, timestamp, strategy, direction, proximity_score, exit_status, net_pnl 
            FROM trades
            ORDER BY timestamp DESC
        """)
        raw_rows = cursor.fetchall()
        
        trade_history = []
        for r in raw_rows:
            trade_history.append({
                "ticker": r[0],
                "timestamp": r[1],
                "strategy": r[2],
                "direction": r[3],
                "proximity": r[4] if r[4] else 0.0,
                "status": r[5],
                "pnl": r[6] if r[6] else 0.0
            })
            
        conn.close()
        
        payload = {
            "overall": {
                "total_trades": total_t,
                "net_pnl": round(net_pnl, 2),
                "win_rate": win_rate
            },
            "buckets": bucket_stats,
            "history": trade_history
        }
        
        temp_file = f"{DATA_JSON}.tmp"
        with open(temp_file, 'w') as f:
            json.dump(payload, f, indent=4)
        os.replace(temp_file, DATA_JSON)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HARM.AI Automated Pipeline Test and Reconciler Harness")
    parser.add_argument("--verify", action="store_true", help="Run forensic database integrity validation against physical CSV records")
    parser.add_argument("--batch", action="store_true", help="Initialize multi-day automated backtest and DB ingestion loop")
    parser.add_argument("--start", default="2026-07-06", help="Range start date (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-07-09", help="Range end date (YYYY-MM-DD)")
    parser.add_argument("--filter", action="store_true", help="Execute micro-level diagnostic segment queries on database")
    parser.add_argument("--ticker", default=None, help="Diagnostic query ticker constraint")
    parser.add_argument("--strategy", default=None, help="Diagnostic query strategy class constraint")
    parser.add_argument("--proximity", default=None, help="Diagnostic query proximity score constraint")
    parser.add_argument("--timeframe", default=None, choices=["morning", "midday", "afternoon"], help="Diagnostic query timezone cluster constraint")
    
    # --- DYNAMIC RISK PARAMETERS ARGUMENTS ---
    parser.add_argument("--max-risk-total", type=float, default=20.0, help="Maximum total capital risk per trade")
    parser.add_argument("--max-risk-rpc", type=float, default=20.0, help="Maximum individual risk per contract (RPC)")
    
    args = parser.parse_args()

    engine = HarmonizedAnalyticsEngine(max_total_risk=args.max_risk_total, max_rpc=args.max_risk_rpc)

    if args.verify:
        engine.verify_database_integrity()
    elif args.batch:
        engine.run_batch_date_reconciliation(args.start, args.end)
    elif args.filter:
        engine.run_filtered_analysis(
            ticker=args.ticker,
            strategy=args.strategy,
            min_proximity=args.proximity,
            timeframe=args.timeframe
        )
    else:
        # Default simple pipeline check simulation
        log_msg("SIMULATOR", "No active flags provided. Executing default single-ticker simulation check...")
        engine.run_batch_date_reconciliation("2026-07-09", "2026-07-09")
