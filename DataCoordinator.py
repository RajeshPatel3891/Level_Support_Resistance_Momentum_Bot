import json
import os
import argparse
from datetime import datetime

def print_cat_drop():
    """Drops a friendly ASCII cat into the terminal."""
    cat = r"""
      |\---/|
      | o_o |
       \_^_/
    """
    print(cat)
    print("[+] Data consolidation complete. Meow!")

def consolidate_data(tickers, target_date, output_dir="data/processed"):
    """
    Consolidates individual ticker files into a single unified JSON.
    Verifies that the data within the files matches the requested date.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    consolidated = {}
    
    for ticker in tickers:
        filename = f"{ticker}_{target_date}.json"
        if not os.path.exists(filename):
            print(f"[!] Error: {filename} not found. Please run FetchHistoricalData first.")
            continue
            
        with open(filename, 'r') as f:
            data = json.load(f)
            
            # Simple validation: Check if first entry date matches target_date
            if data and "time" in data[0]:
                entry_date = data[0]['time'].split('T')[0]
                if entry_date != target_date:
                    print(f"[!] Warning: Date mismatch for {ticker}. Expected {target_date}, found {entry_date}")
            
            consolidated[ticker] = data
            
    output_path = os.path.join(output_dir, f"market_data_{target_date}.json")
    with open(output_path, 'w') as f:
        json.dump(consolidated, f, indent=4)
        
    print(f"[+] Successfully consolidated data for {tickers} into {output_path}")
    print_cat_drop()
    return output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Consolidate market data files.")
    parser.add_argument("--tickers", required=True, help="Space-separated list of tickers")
    parser.add_argument("--date", required=True, help="Date in YYYY-MM-DD format")
    args = parser.parse_args()
    
    tickers_list = args.tickers.split()
    consolidate_data(tickers_list, args.date)
