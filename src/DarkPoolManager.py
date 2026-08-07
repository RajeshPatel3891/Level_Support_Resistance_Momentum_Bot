import collections

class DarkPoolManager:
    def __init__(self, window_size=50):
        # Stores last N block trades per ticker
        self.history = collections.defaultdict(lambda: collections.deque(maxlen=window_size))
        
    def add_trade(self, ticker, price, volume):
        # Filter for "Institutional Size" (e.g., > 10,000 shares)
        if volume > 10000:
            self.history[ticker].append({'p': price, 'v': volume})
            
    def get_vwap(self, ticker):
        trades = self.history[ticker]
        if not trades: return None
        total_val = sum(t['p'] * t['v'] for t in trades)
        total_vol = sum(t['v'] for t in trades)
        return total_val / total_vol if total_vol > 0 else None
