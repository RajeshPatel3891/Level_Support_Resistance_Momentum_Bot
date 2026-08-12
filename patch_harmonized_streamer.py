import re

with open("harmonized_bot_streamer.py", "r") as f:
    code = f.read()

# Replace DB sync method to pull full row schema (occ_symbol, shares, entry_price)
new_sync_method = """def sync_active_positions_from_db(self):
        \"\"\"Pulls active positions from database into standard Python dictionary.\"\"\"
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM trades WHERE exit_status = 'ACTIVE'")
        rows = cursor.fetchall()
        conn.close()

        self.active_monitors = {}
        for row in rows:
            ticker = row["ticker"]
            if ticker not in self.active_monitors:
                self.active_monitors[ticker] = []
                
            keys = row.keys()
            occ = row["occ_symbol"] if "occ_symbol" in keys else (row["option_symbol"] if "option_symbol" in keys else ticker)
            shares = abs(float(row["shares"])) if ("shares" in keys and row["shares"]) else 5.0
            entry_p = float(row["spot_price"] or row["entry_price"] or 0.0)
            
            self.active_monitors[ticker].append({
                "db_id": row["id"],
                "entry_price": entry_p,
                "stop_loss": float(row["stop_loss"] or round(entry_p * 0.80, 2)),
                "take_profit": float(row["take_profit"] or round(entry_p * 1.50, 2)),
                "strategy": str(row["strategy"]),
                "direction": str(row["direction"]),
                "occ_symbol": str(occ),
                "shares": shares
            })"""

if "def sync_active_positions_from_db(self):" in code:
    pattern = r"def sync_active_positions_from_db\(self\):.+?self\.active_monitors\[ticker\]\.append\(\{.+?\}\)"
    code = re.sub(pattern, new_sync_method, code, flags=re.DOTALL)
    with open("harmonized_bot_streamer.py", "w") as f:
        f.write(code)
    print("[✓] Cleanly patched harmonized_bot_streamer.py without signature or runtime errors!")
else:
    print("[!] Target method not found in harmonized_bot_streamer.py")
