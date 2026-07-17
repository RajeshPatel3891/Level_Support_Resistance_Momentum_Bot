import sqlite3, datetime, sys, os, importlib, argparse
sys.path.append(os.getcwd())

def inject_forced_trade(ticker, side, price, qty, is_live):
    # Determine the live flag status (1 for live, 0 for simulation)
    live_status = 1 if is_live else 0
    mode_label = "LIVE" if live_status == 1 else "SIMULATION"

    try:
        # Load the playbook dynamically
        playbook = importlib.import_module(f"src.{ticker.lower()}_playbook")
        risk = playbook.calculate_risk_parameters(float(price), side)
    except Exception as e:
        print(f"[!] Playbook load error (Ensure src/{ticker.lower()}_playbook.py exists): {e}")
        return

    conn = sqlite3.connect("harm_telemetry.db")
    cursor = conn.cursor()
    
    query = """
    INSERT INTO trades (
        ticker, timestamp, strategy, direction, support_level, 
        spot_price, stop_loss, take_profit, exit_status, net_pnl, is_live
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(query, (
        ticker.upper(), timestamp, "FORCE_INJECT", side.upper(), 
        float(price) * 0.99, float(price), risk["stop_loss"], risk["tp1"], 
        "ACTIVE", 0.0, live_status
    ))
    
    conn.commit()
    conn.close()
    print(f"[✓] Successfully injected {ticker.upper()} {side.upper()} at ${price} as {mode_label} into telemetry.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="🛸 HARM.AI // Force Execution Trade Injector")
    parser.add_argument("ticker", type=str, help="Stock Ticker (e.g., NVDA, INTC)")
    parser.add_argument("side", type=str, choices=["CALL", "PUT"], help="Direction of option trigger")
    parser.add_argument("price", type=float, help="Simulated spot/entry price")
    parser.add_argument("qty", type=int, help="Number of option contracts")
    parser.add_argument("--live", action="store_true", help="Flag to mark this as a real LIVE trade in the database")

    args = parser.parse_args()
    inject_forced_trade(args.ticker, args.side, args.price, args.qty, args.live)
