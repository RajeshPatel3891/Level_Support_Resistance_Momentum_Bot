import sqlite3

DB_PATH = 'src/harm_telemetry.db'

def get_latest_gex_context(ticker):
    """
    Queries the local SQLite database to fetch the most recent GEX metrics for a ticker.
    Returns a dictionary with telemetry data, or None if no record exists.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Pull the absolute freshest single record for the requested symbol
        cursor.execute('''
            SELECT underlying_price, net_gex, gex_label, timestamp 
            FROM gex_telemetry 
            WHERE ticker = ? 
            ORDER BY id DESC 
            LIMIT 1
        ''', (ticker.upper(),))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "underlying_price": row[0],
                "net_gex": row[1],
                "gex_label": row[2],
                "timestamp": row[3]
            }
    except Exception as e:
        print(f"[-] Error reading local GEX database: {e}")
        
    return None
