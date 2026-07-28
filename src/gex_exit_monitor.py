import sqlite3, json, time, os, sys
sys.path.append(os.getcwd())

try:
    from src.HarmonizedDispatch import force_exit_all
    DISPATCH_AVAILABLE = True
except ImportError:
    DISPATCH_AVAILABLE = False

LEVELS_FILE = "/home/ubuntu/Level_Support_Resistance_Momentum_Bot/trading_levels.json"

def get_active_trades():
    conn = sqlite3.connect("harm_telemetry.db", timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("SELECT id, ticker, spot_price, stop_loss, take_profit, is_live FROM trades WHERE exit_status = 'ACTIVE'")
    trades = cursor.fetchall()
    conn.close()
    return trades

def update_trailing_stop(trade_id, ticker, new_stop_floor, reason="TRAILING"):
    conn = sqlite3.connect("harm_telemetry.db", timeout=30.0)
    conn.execute("UPDATE trades SET stop_loss = ? WHERE id = ?", (new_stop_floor, trade_id))
    conn.commit()
    conn.close()
    print(f"[📈 {reason}] Raised stop floor for {ticker} to ${new_stop_floor:.2f}")

def execute_exit_routing(trade_id, ticker, current_price, is_live, exit_type):
    conn = sqlite3.connect("harm_telemetry.db", timeout=30.0)
    if is_live == 1:
        if DISPATCH_AVAILABLE:
            print(f"[🚨 LIVE EXECUTOR] [{exit_type}] Dispatching market exit order for {ticker} via HarmonizedDispatch...")
            success = force_exit_all(ticker, force_market=True)
            if success:
                conn.execute("UPDATE trades SET exit_status = 'EXITED', net_pnl = ((? - spot_price)/spot_price)*100 WHERE id = ?", (current_price, trade_id))
                print(f"[✓] Live [{exit_type}] exit confirmed and logged for {ticker}.")
            else:
                print(f"[!] Live exit FAILED via broker API. Marking as FAILED_EXIT.")
                conn.execute("UPDATE trades SET exit_status = 'FAILED_EXIT' WHERE id = ?", (trade_id,))
        else:
            print(f"[!] Critical: Trade is marked LIVE but HarmonizedDispatch is unavailable!")
    else:
        pnl_label = 'SIM_PROFIT' if exit_type == 'TAKE_PROFIT' else f'SIM_{exit_type}'
        print(f"[🔥 SIM EXECUTOR] [{exit_type}] Executing local DB bypass for {ticker}.")
        conn.execute("UPDATE trades SET exit_status = ?, net_pnl = ((? - spot_price)/spot_price)*100 WHERE id = ?", (pnl_label, current_price, trade_id))
        print(f"[✓] Simulated status ({pnl_label}) updated safely in telemetry database.")
    conn.commit()
    conn.close()

def monitor_loop():
    print("[*] GEX Monitor: Running with Integrated Options Regime Protection (Walls/Flips).")
    while True:
        if not os.path.exists(LEVELS_FILE):
            time.sleep(10)
            continue
            
        with open(LEVELS_FILE, 'r') as f:
            levels = json.load(f)

        active_trades = get_active_trades()
        for trade_id, ticker, entry_price, current_stop_loss, take_profit, is_live in active_trades:
            ticker_data = levels.get(ticker, {})
            curr_price = ticker_data.get("last_price", entry_price)
            
            gamma_flip = ticker_data.get("gamma_flip", entry_price)
            call_wall = ticker_data.get("call_wall", take_profit)
            
            mode_tag = "LIVE" if is_live == 1 else "SIM"
            pnl_pct = ((curr_price - entry_price) / entry_price) * 100
            print(f"[⚙️][{mode_tag}] {ticker} | Price: {curr_price} | PnL: {pnl_pct:+.2f}% | Stop: ${current_stop_loss:.2f} | Flip: {gamma_flip}")

            # --- DYNAMIC TAKE PROFIT CAP (GEX LOGIC #2) ---
            if take_profit > call_wall:
                take_profit = call_wall - 0.10
                print(f"[🎯 GEX ADJUST] Capped Take Profit target below Call Wall resistance for {ticker} at ${take_profit:.2f}")

            # --- GLOBAL VOLATILITY REGIME SHIFT PROTECTION (GEX LOGIC #1) ---
            # If we are in negative GEX territory, IMMEDIATELY tighten stops to protect capital
            if curr_price < gamma_flip:
                squeezed_floor = curr_price * 0.9925  # Extremely tight 0.75% stop buffer
                if squeezed_floor > current_stop_loss:
                    update_trailing_stop(trade_id, ticker, squeezed_floor, reason="GEX SQUEEZE")
                    current_stop_loss = squeezed_floor

            # --- STANDARD TRAILING ENGINE ---
            elif curr_price > entry_price:
                calculated_floor = curr_price * 0.98  # Standard 2.0% trailing leeway
                if calculated_floor > current_stop_loss:
                    update_trailing_stop(trade_id, ticker, calculated_floor, reason="TRAILING")
                    current_stop_loss = calculated_floor

            # --- MATCH ENGINE BOUNDARIES ---
            if curr_price >= take_profit:
                execute_exit_routing(trade_id, ticker, curr_price, is_live, "TAKE_PROFIT")
            elif curr_price < current_stop_loss:
                execute_exit_routing(trade_id, ticker, curr_price, is_live, "TRAILING_STOP")
            
        time.sleep(10)

if __name__ == "__main__":
    monitor_loop()
