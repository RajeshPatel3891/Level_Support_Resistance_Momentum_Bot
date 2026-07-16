import sqlite3
import csv
import glob
import os

def ingest_production():
    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    # We remove only production records (is_live=1) so we don't duplicate if run twice
    cursor.execute("DELETE FROM trades WHERE is_live = 1")
    
    files_processed = 0
    trades_ingested = 0

    # Target files that contain "_audit.csv" but NOT "_SIM_"
    for filepath in glob.glob("*_audit.csv"):
        if "_SIM_" in filepath: continue
        
        ticker = filepath.split('_')[0]
        with open(filepath, 'r') as f:
            reader = csv.reader(f)
            next(reader, None) # Skip header
            
            entry = None
            for ts, price, action, conv, res, notes in reader:
                price = float(price)
                if action == "ENTER":
                    entry = {"ts": ts, "price": price}
                elif action == "EXIT" and entry:
                    # Calculate PnL matching the logic used in ReconcileProduction.py
                    pnl = 500.0 * ((price - entry['price']) / entry['price']) * 10.0
                    if res == "STOP_LOSS": pnl = -abs(pnl)
                    
                    cursor.execute("""
                        INSERT INTO trades (ticker, timestamp, strategy, direction, exit_status, net_pnl, is_live)
                        VALUES (?, ?, 'PRODUCTION_SCALP', 'LONG', ?, ?, 1)
                    """, (ticker, ts, res, pnl))
                    
                    trades_ingested += 1
                    entry = None
        files_processed += 1
        
    conn.commit()
    conn.close()
    print(f"[✓] Ingested {trades_ingested} trades from {files_processed} production files.")

ingest_production()
