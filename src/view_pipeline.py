import os
import requests
import sqlite3
import argparse
from dotenv import load_dotenv

load_dotenv()

def get_headers():
    token = os.getenv("TRADIER_SANDBOX_TOKEN")
    return {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

def get_live_quote(symbol):
    try:
        r = requests.get(f"https://sandbox.tradier.com/v1/markets/quotes?symbols={symbol}", headers=get_headers())
        if r.status_code == 200:
            quote = r.json().get('quotes', {}).get('quote', {})
            return quote[0] if isinstance(quote, list) else quote
    except: 
        return {}
    return {}

def get_db_tickers_by_status(statuses):
    try:
        from HarmonizedDispatch import get_db_connection
        conn = get_db_connection("harm_telemetry.db")
        placeholders = ",".join("?" for _ in statuses)
        query = f"""
            SELECT ticker, spot_price, exit_status 
            FROM trades 
            WHERE id IN (
                SELECT MAX(id) 
                FROM trades 
                WHERE exit_status IN ({placeholders}) 
                GROUP BY ticker
            )
        """
        rows = conn.execute(query, statuses).fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"[-] Database Query Error: {e}")
        return []
def display_dashboard(statuses):
    active_trades = get_db_tickers_by_status(statuses)
    
    print("=" * 105)
    print("🛰️  HARM.AI // LIVE P&L PROXIMITY FEED")
    print(f"Filter Statuses: {', '.join(statuses)}")
    print("=" * 105)
    
    if not active_trades:
        print("Portfolio is flat or no records found matching status filters.")
    else:
        for ticker, cost_basis, status in active_trades:
            quote = get_live_quote(ticker)
            last_price = float(quote.get('last', 0))
            # Calculate P&L %
            pnl_pct = ((last_price - cost_basis) / cost_basis) * 100 if cost_basis > 0 else 0
            # Feed display with status column added for clarity
            print(f"Asset: {ticker:<12} | Last: ${last_price:<8.2f} | Basis: ${cost_basis:<8.2f} | P&L: {pnl_pct:>+7.2f}% | Status: {status}")

    print("\n[⚙️] System synced.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HARM.AI Live Feed Viewer")
    parser.add_argument(
        "--status", 
        type=str, 
        default="ACTIVE", 
        help="Comma-separated statuses to monitor (e.g. ACTIVE,SIM_TRAILING_STOP)"
    )
    args = parser.parse_args()
    
    # Split comma-separated inputs (e.g., "open,filled" -> ["open", "filled"])
    status_list = [s.strip() for s in args.status.split(",") if s.strip()]
    
    # Handle older legacy terms to match database expectations automatically
    mapped_statuses = []
    for s in status_list:
        if s.lower() in ["open", "filled"]:
            mapped_statuses.append("ACTIVE")
        else:
            mapped_statuses.append(s)
            
    # Ensure we don't pass an empty status array
    if not mapped_statuses:
        mapped_statuses = ["ACTIVE"]
        
    display_dashboard(mapped_statuses)
