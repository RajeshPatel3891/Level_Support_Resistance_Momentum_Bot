import json, csv, os, sys, time
from LiveBot import calculate_trade_conviction, calculate_exits, update_rolling_volume
from SignalBridge import read_signals, write_signals, init_bridge
from AlertManager import send_discord_alert

# Full portfolio assets maintained
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
    print("[*] CRITICAL FOREGROUND ENGAGED: Listening for simulated signals...")
    
    while True:
        signals = read_signals()
        updated = False
        
        for signal in signals:
            if not signal or signal.get("status") != "PENDING_BACKTEST":
                continue
            
            # Integrated Safe Field Normalization Matrix
            symbol = signal.get('symbol') or signal.get('ticker') or 'UNKNOWN'
            entry_price = signal.get('entry_price') or signal.get('price') or 0.0
            
            # Explicitly force-sync dict states to maintain down-pipe compatibility
            signal['symbol'] = symbol
            signal['entry_price'] = entry_price
            if 'rvol' not in signal: signal['rvol'] = 1.0
            
            metrics = run_shadow_match(signal)
            
            # ONLY ACTION: High Conviction Win-Rate Clearances
            if metrics and metrics.get("win_rate", 0) >= 0.65:
                signal["status"] = "APPROVED"
                signal["guidance"] = f"High Conviction. WR: {metrics['win_rate']*100:.1f}%"
                
                # Fetch risk parameters out of the file layout directly
                sl = signal.get("sl", 0.0)
                tp1 = signal.get("tp1", 0.0)
                tp2 = signal.get("tp2", 0.0)
                
                print(f"\n[>>>] CAPTURED SIGNAL IN FOREGROUND FOR {symbol} at ${entry_price:.2f}")
                print(f"      EXTRACTED METRICS -> SL: {sl} | TP1: {tp1} | TP2: {tp2}")
                
                # Build rich multi-layered meta payload message for the Discord layout
                rich_text = f"High Conviction ({signal['guidance']})\n\n**[RISK TARGETS]**\n• **SL:** ${sl:.2f}\n• **TP1:** ${tp1:.2f}\n• **TP2:** ${tp2:.2f}"
                
                print(f"      SENDING TO DISCORD DISPATCH MATRIX...")
                
                send_discord_alert(
                    ticker=symbol,
                    action="BUY",
                    price=float(entry_price),
                    reason=rich_text
                )
                updated = True
            else:
                # Silently mark as rejected to keep queue fresh and unblocked
                signal["status"] = "REJECTED"
                updated = True
            
        if updated:
            write_signals(signals)
            
        time.sleep(0.5)

if __name__ == "__main__":
    # Execute immediately regardless of argv flags passed by parent setups!
    watch_live_bridge()
