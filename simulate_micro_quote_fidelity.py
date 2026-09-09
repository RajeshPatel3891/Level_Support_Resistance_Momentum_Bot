import os, sys, requests
from dotenv import load_dotenv

if os.path.exists('.env.prod'):
    load_dotenv('.env.prod', override=True)
else:
    load_dotenv(override=True)

TOKEN = os.getenv("TRADIER_PROD_TOKEN") or os.getenv("TRADIER_TOKEN")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}

class MicroQuoteFidelityTester:
    def __init__(self, symbol, entry_px, shares=2, config_flags=None):
        self.symbol = symbol
        self.entry_px = float(entry_px)
        self.shares = int(shares)
        self.flags = config_flags or {}
        
        self.peak_mark = self.entry_px
        self.base_stop = max(0.10, self.entry_px * 0.65) if self.entry_px <= 1.00 else round(self.entry_px * 0.70, 2)
        self.active_stop = self.base_stop
        self.partial_taken = False
        self.shares_remaining = self.shares
        
        # Debounce tracking
        self.breach_pending = False
        self.breach_tick_idx = None

    def fetch_trade_anchors(self):
        url = "https://api.tradier.com/v1/markets/timesales"
        params = {
            "symbol": self.symbol,
            "interval": "tick",
            "start": "2026-09-08 09:30",
            "end": "2026-09-08 16:00"
        }
        r = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json().get("series", {}).get("data", [])
            return [data] if isinstance(data, dict) else data
        return []

    def generate_micro_quotes(self, trades):
        quotes = []
        for i, trade in enumerate(trades):
            last_px = float(trade.get("price") or 0.0)
            t_str = trade.get("time", "")

            spread = 0.02 if last_px < 0.50 else 0.03
            bid = round(max(0.01, last_px - spread / 2.0), 2)
            ask = round(bid + spread, 2)
            mark = round((bid + ask) / 2.0, 2)

            quotes.append({"time": t_str, "bid": bid, "ask": ask, "mark": mark, "is_synthetic": False})

            if i < len(trades) - 1:
                next_px = float(trades[i+1].get("price") or last_px)
                mid_px = round((last_px + next_px) / 2.0, 2)
                quotes.append({
                    "time": t_str,
                    "bid": round(max(0.01, mid_px - spread / 2.0), 2),
                    "ask": round(mid_px + spread / 2.0, 2),
                    "mark": mid_px,
                    "is_synthetic": True
                })
        return quotes

    def run_replay(self):
        trades = self.fetch_trade_anchors()
        if not trades:
            print("[-] No trade anchors found.")
            return

        quotes = self.generate_micro_quotes(trades)
        print(f"\n==========================================================================")
        print(f"🔬 HIGH-FIDELITY DEBOUNCED REPLAY: {self.symbol}")
        print(f"[*] Anchors: {len(trades)} Trades | Total Reconstructed Quotes: {len(quotes)}")
        print(f"[*] Flags: {self.flags}")
        print(f"[*] Basis: ${self.entry_px:.2f} | Base Stop: ${self.base_stop:.2f} | Qty: {self.shares}")
        print(f"==========================================================================")

        for idx, q in enumerate(quotes):
            t = q["time"]
            bid = q["bid"]
            ask = q["ask"]
            mark = q["mark"]

            # --- STRESS INJECTIONS ---
            if self.flags.get("inject_flash_dip") and idx == self.flags.get("flash_dip_idx", 80):
                bid = round(self.entry_px * 0.45, 2)
                ask = round(bid + 0.02, 2)
                mark = round((bid + ask) / 2.0, 2)
                print(f"  [{t}] ⚡ [STRESS INJECT] 1-Tick flash dip forced: Mark ${mark:.2f} at tick #{idx}")

            if mark > self.peak_mark:
                self.peak_mark = mark

            peak_gain_pct = ((self.peak_mark - self.entry_px) / self.entry_px) * 100.0
            current_pnl_pct = ((mark - self.entry_px) / self.entry_px) * 100.0
            drawdown_from_peak_pct = ((self.peak_mark - mark) / self.peak_mark) * 100.0 if self.peak_mark > 0 else 0.0

            # MTTP dynamic trailing steps
            if peak_gain_pct >= 40.0:
                target_stop = round(self.entry_px * 1.25, 2)
            elif peak_gain_pct >= 30.0:
                target_stop = round(self.entry_px * 1.15, 2)
            elif peak_gain_pct >= 20.0:
                target_stop = round(self.entry_px * 1.08, 2)
            elif peak_gain_pct >= 15.0:
                target_stop = round(self.entry_px * 1.00, 2)
            else:
                target_stop = self.base_stop

            self.active_stop = max(self.active_stop, target_stop)

            # Partial scale out
            if not self.partial_taken and self.shares_remaining >= 2 and current_pnl_pct >= 20.0:
                self.shares_remaining -= 1
                self.partial_taken = True
                print(f"  [{t}] ⚖️ [MTTP SCALE OUT] Sold 1x @ Mark ${mark:.2f} (+{current_pnl_pct:.1f}%). Runner shares: {self.shares_remaining}")

            # --- DEBOUNCED EXIT LOGIC ---
            if mark <= self.active_stop:
                allowable_dd = 30.0 if peak_gain_pct >= 50.0 else (25.0 if peak_gain_pct >= 30.0 else (20.0 if peak_gain_pct >= 15.0 else 15.0))
                if peak_gain_pct >= 20.0 and drawdown_from_peak_pct < allowable_dd:
                    self.breach_pending = False
                    continue

                if not self.breach_pending:
                    self.breach_pending = True
                    self.breach_tick_idx = idx
                    print(f"  [{t}] ⚠️ [STOP WARNING] Tick #{idx} pierced stop (${mark:.2f} <= ${self.active_stop:.2f}). Awaiting confirmation...")
                    continue
                else:
                    print(f"  [{t}] 🛑 [CONFIRMED EXIT] Breach verified across consecutive ticks ({self.breach_tick_idx} -> {idx}). Executing @ ${mark:.2f}")
                    print(f"      -> Reason: DYNAMIC_TRAIL_STOP | Peak: ${self.peak_mark:.2f} (+{peak_gain_pct:.1f}%) | Exit PnL: {current_pnl_pct:+.2f}%")
                    return
            else:
                if self.breach_pending:
                    print(f"  [{t}] 🛡️ [DEBOUNCE FILTERED] Wick rejected. Price recovered to ${mark:.2f} at tick #{idx}. Position retained.")
                    self.breach_pending = False

        print(f"\n[✓] Survived full session tape without breach. Final Mark: ${mark:.2f} ({current_pnl_pct:+.2f}%)")

if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "GDX260911P00098000"
    entry = float(sys.argv[2]) if len(sys.argv) > 2 else 1.36
    
    flags = {
        "inject_flash_dip": True,
        "flash_dip_idx": 80
    }

    tester = MicroQuoteFidelityTester(symbol, entry_px=entry, shares=2, config_flags=flags)
    tester.run_replay()
