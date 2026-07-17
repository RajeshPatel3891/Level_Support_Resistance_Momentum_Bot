import re

with open('src/view_pipeline.py', 'r') as f:
    content = f.read()

# The block to inject
patch = """    # HYBRID OVERRIDE: If API returns empty, check local DB
    if not positions:
        try:
            import sqlite3
            conn = sqlite3.connect("harm_telemetry.db")
            cursor = conn.cursor()
            cursor.execute("SELECT ticker, spot_price FROM trades WHERE exit_status = 'ACTIVE'")
            rows = cursor.fetchall()
            positions = [{"symbol": row[0], "cost_basis": row[1], "quantity": 1} for row in rows]
            conn.close()
        except Exception:
            pass
"""

# Inject after fetch_positions() call
new_content = re.sub(r'(positions = fetch_positions\(\))', r'\1\n' + patch, content)

with open('src/view_pipeline.py', 'w') as f:
    f.write(new_content)
