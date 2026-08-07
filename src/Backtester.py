import pandas as pd
from src.SignalEngine import analyze_trade

class Backtester:
    def __init__(self, dpl_levels):
        self.dpl_levels = dpl_levels
        self.results = []

    def run_simulation(self, ticker, df, tp_pct=0.20, sl_pct=0.30, window_min=999):
        levels = self.dpl_levels.get(ticker)
        if not levels: return []
        
        in_trade = False
        trade_data = {}
        
        # Accessing the underlying values directly to avoid Series/Frame index issues
        close_values = df['Close'].values
        
        for i in range(20, len(df) - 6):
            subset = df.iloc[:i]
            price = float(close_values[i])
            
            if not in_trade:
                signal = analyze_trade(ticker, price, levels['support'], levels['resistance'], subset)
                if signal['action'] != 'WAIT':
                    in_trade = True
                    
                    # Parse dynamic ATR Exits from the string if they exist
                    dyn_tp = None
                    dyn_sl = None
                    if 'TP: $' in signal['reason']:
                        try:
                            parts = signal['reason'].split('TP: $')[1].split(' | SL: $')
                            dyn_tp = float(parts[0])
                            dyn_sl = float(parts[1])
                        except:
                            pass
                            
                    trade_data = {
                        "entry_i": i, 
                        "entry_price": price, 
                        "action": signal['action'], 
                        "start_time": df.index[i],
                        "tp_price": dyn_tp,
                        "sl_price": dyn_sl
                    }
            else:
                elapsed_min = (i - trade_data['entry_i']) * 5
                entry = trade_data['entry_price']
                
                # Corrected check for Long vs Short positions
                is_long = 'BUY' in trade_data['action']
                
                diff = (price - entry) / entry
                profit_move = diff if is_long else -diff
                
                exit_triggered = False
                
                # Use Dynamic ATR targets if available
                if trade_data['tp_price'] and trade_data['sl_price']:
                    if is_long:
                        if price >= trade_data['tp_price'] or price <= trade_data['sl_price']:
                            exit_triggered = True
                    else:
                        if price <= trade_data['tp_price'] or price >= trade_data['sl_price']:
                            exit_triggered = True
                else:
                    # Fallback to static percentages
                    if profit_move >= tp_pct or profit_move <= -sl_pct:
                        exit_triggered = True
                        
                if exit_triggered or elapsed_min >= window_min:
                    self.results.append({**trade_data, "exit_price": price, "pnl": profit_move})
                    in_trade = False
                    
        return self.results
