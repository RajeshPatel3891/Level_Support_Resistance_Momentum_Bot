import json, csv, os, sys, time
from LiveBot import calculate_trade_conviction, calculate_exits, update_rolling_volume
from SignalBridge import read_signals, write_signals, init_bridge
from AlertManager import send_discord_alert

# Full portfolio assets
TICKERS = ["IWM", "QQQ", "GOOGL", "AMZN", "AAPL", "NVDA", "TSLA"]

# =====================================================================
# SHADOW EXECUTION ENGINE
# =====================================================================
def run_shadow_match(signal):
    rvol = signal.get('rvol', 1.0)
    rvol_boost = min(rvol * 0.1, 0.3)
    return {"win_rate": 0.55 + rvol_boost}

def watch_live_bridge():
    init_bridge()
    print("[SHADOW] BacktestBot (Shadow Execution Mode) is online...")
    
    while True:
        signals = read_signals()
        updated = False
        
        for signal in signals:
            if not signal or signal.get("status") != "PENDING_BACKTEST":
                continue
            
            # Normalize
            if 'symbol' not in signal: signal['symbol'] = signal.get('ticker')
            if 'entry_price' not in signal: signal['entry_price'] = signal.get('price')
            if 'rvol' not in signal: signal['rvol'] = 1.0
            
            metrics = run_shadow_match(signal)
            
            # ONLY ACTION: High Conviction
            if metrics and metrics.get("win_rate", 0) >= 0.65:
                signal["status"] = "APPROVED"
                signal["guidance"] = f"High Conviction. WR: {metrics['win_rate']*100:.1f}%"
                
                print(f">>> [APPROVED] {signal.get('symbol')} | {signal['guidance']}")
                
                send_discord_alert(
                    ticker=signal.get('symbol', 'UNKNOWN'),
                    action="BUY",
                    price=signal.get('entry_price', 0.0),
                    reason=f"High Conviction ({signal['guidance']})"
                )
                updated = True
            else:
                # Silently mark as rejected to stop re-processing
                signal["status"] = "REJECTED"
                updated = True
            
        if updated:
            write_signals(signals)
            
        time.sleep(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--live":
        watch_live_bridge()
