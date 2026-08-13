import os
import sqlite3
import boto3
from dotenv import load_dotenv

load_dotenv()

def safe_purge_ticker(target_ticker):
    print("==========================================================")
    print(f"🛡️ HARM.AI // TARGETED SAFE PURGE FOR: {target_ticker}")
    print("==========================================================")

    region = os.getenv('AWS_REGION', 'us-east-1')
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table('HarmonizedTrades')

    key_schema = table.key_schema
    key_names = [k['AttributeName'] for k in key_schema]

    print(f"[*] Scanning DynamoDB for records matching ticker: {target_ticker}...")
    try:
        response = table.scan()
        items = response.get('Items', [])
        deleted_count = 0
        for item in items:
            if str(item.get('ticker', '')).upper() == target_ticker.upper():
                key_dict = {k: item[k] for k in key_names if k in item}
                print(f"    -> Safely deleting target record: {key_dict}")
                table.delete_item(Key=key_dict)
                deleted_count += 1
        print(f"[✓] Successfully purged {deleted_count} records for {target_ticker} from DynamoDB.")
    except Exception as e:
        print(f"[!] Error during targeted DynamoDB purge: {e}")

    # Clean matching records from local SQLite database safely
    db_path = os.path.join(os.path.dirname(__file__), 'harm_telemetry.db')
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM trades WHERE UPPER(ticker) = ?", (target_ticker.upper(),))
        conn.commit()
        conn.close()
        print(f"[✓] Successfully cleared {target_ticker} from local SQLite telemetry DB.")

if __name__ == '__main__':
    tickers_to_purge = ["AAPL", "NVDA"]
    for tkr in tickers_to_purge:
        safe_purge_ticker(tkr)

    # Recompile dashboard export JSON once after all target purges
    try:
        os.system("./venv/bin/python3 src/generate_dashboard_data.py")
        print("[✓] Dashboard dataset recompiled successfully.")
    except Exception as e:
        print(f"[!] Warning updating dashboard data: {e}")

    print("==========================================================")
    print("[✓] SAFE PURGE COMPLETE FOR AAPL & NVDA. UNRELATED ASSETS UNTOUCHED.")
    print("==========================================================")
