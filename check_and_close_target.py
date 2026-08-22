#!/usr/bin/env python3
"""
HARM.AI // DYNAMIC MULTI-TICKER BRACKET EXIT HELPER
===============================================================================
Usage Examples:
  # Universal target floor ($1.00):
  python3 check_and_close_target.py 1.00

  # SOFI bracket between -$1.00 and +$3.00 | F bracket between -$2.00 and +$2.00
  python3 check_and_close_target.py -tt SOFI=-1.00,3.00 -tt F=-2.00,2.00

  # SOFI target only (+3.00), F bracket (-1.00 to +2.00)
  python3 check_and_close_target.py -tt SOFI=3.00 -tt F=-1.00,2.00
"""

import os
import sys
import argparse
import boto3
from dotenv import load_dotenv
from boto3.dynamodb.conditions import Attr
import src.gex_exit_monitor as gex

if os.path.exists('.env.prod'):
    load_dotenv('.env.prod', override=True)
else:
    load_dotenv(override=True)

def parse_args():
    parser = argparse.ArgumentParser(description="HARM.AI Dynamic Multi-Ticker Bracket Exit Helper")
    parser.add_argument(
        "default_target",
        type=float,
        nargs="?",
        default=None,
        help="Default profit target in dollars for unflagged tickers"
    )
    parser.add_argument(
        "-t", "--target",
        type=float,
        default=None,
        help="Default profit target flag"
    )
    parser.add_argument(
        "-tt", "--ticker-target",
        action="append",
        default=[],
        help="Per-ticker bracket in format TICKER=STOP,TARGET or TICKER=TARGET (e.g., -tt SOFI=-1.00,3.00)"
    )

    args = parser.parse_args()

    global_target = float(os.getenv("TARGET_PROFIT_DOLLARS", 1.00))
    if args.target is not None:
        global_target = args.target
    elif args.default_target is not None:
        global_target = args.default_target

    # Parse ticker brackets: {TICKER: {'stop': float or None, 'target': float}}
    ticker_brackets = {}
    for entry in args.ticker_target:
        if "=" in entry:
            tkr, val_str = entry.split("=", 1)
            tkr = tkr.strip().upper()
            val_str = val_str.strip()
            
            if "," in val_str:
                parts = val_str.split(",")
                try:
                    stop_val = float(parts[0].strip())
                    target_val = float(parts[1].strip())
                    ticker_brackets[tkr] = {'stop': stop_val, 'target': target_val}
                except ValueError:
                    print(f"[!] Invalid numeric bracket format for '{entry}'. Skipping.")
            else:
                try:
                    target_val = float(val_str)
                    ticker_brackets[tkr] = {'stop': None, 'target': target_val}
                except ValueError:
                    print(f"[!] Invalid numeric target for '{entry}'. Skipping.")

    return global_target, ticker_brackets

def scan_and_close_targets(global_target, ticker_brackets):
    dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
    table = dynamodb.Table('HarmonizedTrades')

    res = table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
    active_items = res.get('Items', [])

    if not active_items:
        print(f"[✓] No active positions open in DynamoDB.")
        return

    print(f"[*] Auditing {len(active_items)} active position(s)...")

    for item in active_items:
        ticker = item.get('ticker', '').strip().upper()
        occ_symbol = item.get('occ_symbol', ticker)
        entry_price = float(item.get('entry_price', 0.0))
        shares = int(float(item.get('shares', 1)))

        if entry_price <= 0 or not occ_symbol:
            continue

        # Resolve brackets for ticker
        bracket = ticker_brackets.get(ticker, {'stop': None, 'target': global_target})
        stop_loss = bracket['stop']
        profit_target = bracket['target']

        mark, active_url = gex.get_live_quote(occ_symbol)
        if mark <= 0:
            print(f"[!] Unable to fetch quote for {occ_symbol}. Skipping.")
            continue

        pnl_dollar = round((mark - entry_price) * 100.0 * shares, 2)
        pnl_pct = ((mark - entry_price) / entry_price) * 100.0

        stop_str = f"-${abs(stop_loss):.2f}" if stop_loss is not None else "NONE"
        print(f"[*] {ticker} ({occ_symbol}) | Shares: {shares}x | Entry: ${entry_price:.2f} | Live: ${mark:.2f} | PnL: ${pnl_dollar:+.2f} ({pnl_pct:+.1f}%) | Bracket: [SL: {stop_str} / TP: +${profit_target:.2f}]")

        # 1. Check Take Profit
        if pnl_dollar >= profit_target:
            print(f"[🚀 TAKE PROFIT HIT] {ticker} reached +${pnl_dollar:.2f} >= +${profit_target:.2f}! Executing market sell_to_close...")
            if gex.execute_tradier_close(occ_symbol, ticker, shares, active_url):
                print(f"[✓] {ticker} successfully closed on Tradier.")
                gex.synchronize_dynamo_with_tradier()

        # 2. Check Stop Loss
        elif stop_loss is not None and pnl_dollar <= stop_loss:
            print(f"[🛑 STOP LOSS HIT] {ticker} dropped to ${pnl_dollar:.2f} <= ${stop_loss:.2f}! Executing market sell_to_close...")
            if gex.execute_tradier_close(occ_symbol, ticker, shares, active_url):
                print(f"[✓] {ticker} successfully stopped out on Tradier.")
                gex.synchronize_dynamo_with_tradier()

        else:
            print(f"[🛡️ HOLDING] {ticker} PnL (${pnl_dollar:+.2f}) is safely inside bracket limits.")

if __name__ == "__main__":
    global_target, ticker_brackets = parse_args()
    scan_and_close_targets(global_target, ticker_brackets)
