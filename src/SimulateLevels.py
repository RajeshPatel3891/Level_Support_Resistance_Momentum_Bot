import json
import time
from LiveBot import calculate_exits

def trigger_mock_simulation():
    print("[*] Opening Level Verification Sandbox Engine...")
    
    # Mock data payloads mimicking today's institutional support tests
    mock_signals = [
        {"symbol": "IWM", "entry_price": 300.61, "rvol": 1.2},
        {"symbol": "NVDA", "entry_price": 194.51, "rvol": 1.4},
        {"symbol": "SPY", "entry_price": 743.02, "rvol": 0.9}
    ]
    
    conduit_payload = []
    
    print("[+] Found 3 institutional support line tests in today's data.")
    print("[*] Enriched metrics: Calculating dynamic risk windows for mock targets...")
    
    for sig in mock_signals:
        price = sig["entry_price"]
        rvol = sig["rvol"]
        
        # Calculate true targets on the fly
        sl, tp1, tp2 = calculate_exits(price, rvol)
        
        conduit_payload.append({
            "id": f"{sig['symbol']}_{int(time.time())}",
            "timestamp": time.time(),
            "symbol": sig["symbol"],
            "ticker": sig["symbol"],
            "entry_price": price,
            "price": price,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "rvol": rvol,
            "status": "PENDING_BACKTEST"
        })
        
    # Overwrite into the live signal bridge wire
    with open("active_signals.json", "w") as f:
        json.dump(conduit_payload, f, indent=4)
        
    print("[*] Streaming simulated signals into active SignalBridge conduit file...")

if __name__ == "__main__":
    trigger_mock_simulation()
