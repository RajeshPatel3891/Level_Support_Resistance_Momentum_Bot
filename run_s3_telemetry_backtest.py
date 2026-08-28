#!/usr/bin/env python3
"""
HARM.AI // S3 TELEMETRY PNL & FILL SCORE COMPARISON ENGINE
===============================================================================
Extracts historical entry & exit prices from S3 telemetry DB partitions,
calculates realized PnL per trade, and compares total strategy PnL between:
  1. Standard Midpoint Execution (Baseline)
  2. Predictive Fill Quality Gate (>= 7.5/10 Threshold)
"""

import os
import sys
import gzip
import shutil
import sqlite3
import boto3
import argparse
from datetime import datetime

# Import engine guard modules
from src.smart_cso_injector import (
    calculate_fill_quality_score,
    predict_fill_quality_score
)

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
TELEMETRY_BUCKET = "harmonized-ai-telemetry-bucket"

def discover_all_s3_dates() -> list:
    s3 = boto3.client('s3', region_name=AWS_REGION)
    dates = []
    try:
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=TELEMETRY_BUCKET, Prefix="ticks/", Delimiter='/')
        for page in pages:
            for prefix_info in page.get('CommonPrefixes', []):
                raw_prefix = prefix_info.get('Prefix', '')
                parts = raw_prefix.strip('/').split('/')
                if len(parts) >= 2 and parts[1]:
                    dates.append(parts[1])
    except Exception as e:
        print(f"[!] S3 discovery error: {e}")
    return sorted(list(set(dates)))

def download_and_decompress_s3_db(date_str: str) -> str:
    s3 = boto3.client('s3', region_name=AWS_REGION)
    s3_key = f"ticks/{date_str}/harm_telemetry_{date_str}.db.gz"
    local_gz = f"/tmp/harm_telemetry_{date_str}.db.gz"
    local_db = f"/tmp/backtest_telemetry_{date_str}.db"

    try:
        s3.download_file(TELEMETRY_BUCKET, s3_key, local_gz)
        with gzip.open(local_gz, 'rb') as f_in:
            with open(local_db, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        return local_db
    except Exception:
        return ""

def process_single_date_db(date_str: str, target_tickers: list = None) -> list:
    db_path = download_and_decompress_s3_db(date_str)
    if not db_path or not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query entry AND exit data to calculate realized PnL
    query = """
        SELECT id, ticker, timestamp, direction, spot_price, entry_price, 
               COALESCE(exit_price, 0.0), COALESCE(net_pnl, 0.0), shares, occ_symbol 
        FROM trades
    """
    if target_tickers:
        ticker_list_str = "','".join([t.upper() for t in target_tickers])
        query += f" WHERE UPPER(ticker) IN ('{ticker_list_str}')"

    try:
        cursor.execute(query)
        trades = cursor.fetchall()
    except Exception:
        conn.close()
        if os.path.exists(db_path): os.remove(db_path)
        return []

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='quotes'")
    has_quotes_table = cursor.fetchone() is not None

    date_results = []

    for t in trades:
        t_id, ticker, ts, direction, spot, entry_px, exit_px, logged_pnl, shares, occ = t
        spot = float(spot or 0.0)
        entry_px = float(entry_px or 0.0)
        exit_px = float(exit_px or 0.0)
        logged_pnl = float(logged_pnl or 0.0)
        shares = int(float(shares or 1))
        occ_symbol = occ or ticker

        actual_bid, actual_ask = 0.0, 0.0

        if has_quotes_table and occ_symbol:
            try:
                cursor.execute("""
                    SELECT bid, ask FROM quotes 
                    WHERE (symbol = ? OR symbol = ?) AND timestamp <= ? 
                    ORDER BY timestamp DESC LIMIT 1
                """, (occ_symbol, ticker, ts))
                q_row = cursor.fetchone()
                if q_row and float(q_row[0] or 0) > 0 and float(q_row[1] or 0) > 0:
                    actual_bid, actual_ask = float(q_row[0]), float(q_row[1])
            except Exception:
                pass

        # Fallback quote estimation
        if actual_bid <= 0 or actual_ask <= 0:
            spread_est = 0.04 if entry_px <= 0.20 else 0.02
            actual_bid = max(0.01, round(entry_px - (spread_est / 2.0), 2))
            actual_ask = round(entry_px + (spread_est / 2.0), 2)

        # Calculate Realized PnL
        if logged_pnl != 0.0:
            realized_pnl = logged_pnl
        elif exit_px > 0 and entry_px > 0:
            realized_pnl = round((exit_px - entry_px) * 100.0 * shares, 2)
        else:
            # If position was held to mark, compute PnL against Bid
            realized_pnl = round((actual_bid - entry_px) * 100.0 * shares, 2)

        pnl_pct = ((realized_pnl / (entry_px * 100.0 * shares)) * 100.0) if entry_px > 0 else 0.0

        mock_quote = {
            'bid': actual_bid,
            'ask': actual_ask,
            'bid_size': 10,
            'ask_size': 10,
            'volume': 100
        }
        
        predicted_score, _ = predict_fill_quality_score(mock_quote, side="buy")
        passed_7_5_gate = (predicted_score >= 7.5)

        date_results.append({
            'date': date_str,
            'timestamp': ts,
            'ticker': ticker.upper(),
            'occ_symbol': occ_symbol,
            'entry_px': entry_px,
            'exit_px': exit_px,
            'realized_pnl': realized_pnl,
            'pnl_pct': pnl_pct,
            'predicted_score': predicted_score,
            'passed_7_5_gate': passed_7_5_gate,
            'shares': shares
        })

    conn.close()
    if os.path.exists(db_path): os.remove(db_path)
    gz_path = f"/tmp/harm_telemetry_{date_str}.db.gz"
    if os.path.exists(gz_path): os.remove(gz_path)

    return date_results

def run_pnl_comparison_backtest(target_tickers: list = None, specific_date: str = None):
    print("=" * 95)
    print("💰 HARM.AI // REALIZED PNL COMPARISON: UNFILTERED (5.0) VS. PREDICTIVE GATE (>=7.5)")
    print("=" * 95)

    dates_to_run = [specific_date] if specific_date else discover_all_s3_dates()
    if not dates_to_run:
        print("[-] No date partitions found in S3.")
        return

    all_results = []
    for d in dates_to_run:
        res = process_single_date_db(d, target_tickers)
        if res:
            all_results.extend(res)

    if not all_results:
        print("\n[-] Zero matching historical trade records found.")
        return

    trades_passed_7_5 = [r for r in all_results if r['passed_7_5_gate']]
    trades_rejected_7_5 = [r for r in all_results if not r['passed_7_5_gate']]

    print(f"\n{'DATE':<10} | {'TICKER':<6} | {'OCC SYMBOL':<20} | {'ENTRY':<7} | {'SCORE':<7} | {'REALIZED PNL':<14} | {'7.5+ GATE'}")
    print("-" * 95)

    for r in all_results[:20]:
        gate_status = "🟢 PASSED" if r['passed_7_5_gate'] else "🔴 REJECTED"
        pnl_str = f"${r['realized_pnl']:+.2f} ({r['pnl_pct']:+.1f}%)"
        print(f"{r['date']:<10} | {r['ticker']:<6} | {r['occ_symbol']:<20} | ${r['entry_px']:<6.2f} | {r['predicted_score']:<4.1f}/10 | {pnl_str:<14} | {gate_status}")

    if len(all_results) > 20:
        print(f"... and {len(all_results) - 20} more historical trades.")

    total_unfiltered_pnl = sum(r['realized_pnl'] for r in all_results)
    total_gated_pnl = sum(r['realized_pnl'] for r in trades_passed_7_5)
    rejected_loss_saved = sum(r['realized_pnl'] for r in trades_rejected_7_5)

    print("\n" + "=" * 95)
    print("📊 REALIZED PNL & PERFORMANCE SUMMARY MATRIX")
    print("=" * 95)
    print(f" Total Trades Scanned                : {len(all_results)}")
    print(f" Trades Passing 7.5+ Gate            : {len(trades_passed_7_5)} ({len(trades_passed_7_5)/len(all_results)*100.0:.1f}%)")
    print(f" Bad/Illiquid Trades Filtered        : {len(trades_rejected_7_5)} ({len(trades_rejected_7_5)/len(all_results)*100.0:.1f}%)")
    print("-" * 95)
    print(f" Total Realized PnL (Unfiltered Mid): ${total_unfiltered_pnl:+.2f}")
    print(f" Total Realized PnL (7.5+ Gate)     : ${total_gated_pnl:+.2f}")
    print(f" Net PnL Delta (Protected Capital)  : ${total_gated_pnl - total_unfiltered_pnl:+.2f}")
    print("=" * 95)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run S3 Realized PnL Comparison Backtest")
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("-t", "--ticker", action="append", default=[])
    
    args = parser.parse_args()
    parsed_tickers = []
    for entry in args.ticker:
        if "," in entry:
            parsed_tickers.extend([item.strip().upper() for item in entry.split(",") if item.strip()])
        else:
            parsed_tickers.append(entry.strip().upper())

    run_pnl_comparison_backtest(target_tickers=parsed_tickers, specific_date=args.date)
