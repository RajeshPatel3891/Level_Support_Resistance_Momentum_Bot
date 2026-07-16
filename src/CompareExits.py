import os
import sys
import json
import csv
import argparse
import ijson
from datetime import datetime

# --- SYSTEM PATH RESOLUTION ---
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.append(CURRENT_DIR)

PARENT_DIR = os.path.dirname(CURRENT_DIR)
LEVELS_FILE = os.path.join(PARENT_DIR, 'trading_levels.json')

# Safe import wrapper for LiveBot
try:
    import LiveBot
    from LiveBot import calculate_trade_conviction, calculate_exits
except ImportError:
    LiveBot = None
    def calculate_trade_conviction(*args, **kwargs):
        return {"conviction": "LOW", "action": "PASS"}
    def calculate_exits(price):
        return (price - 0.50, price + 1.00, None)

TICKERS = ["SPY", "QQQ", "NVDA", "IWM", "AMZN", "AAPL", "MSFT", "TSLA"]

class EvaluationHarness:
    def __init__(self, date="2026-07-07"):
        self.target_date = date
        self.range_safeguard = 0.20
        self.levels_cache = {}
        
        # Load Levels
        if os.path.exists(LEVELS_FILE):
            with open(LEVELS_FILE, "r") as f:
                self.levels_cache = json.load(f).get("levels", {})

    def run_backtest_pass(self, ticker, method="standard"):
        """
        Runs a simulation pass using the specified exiting method.
        method: 'standard' (Method A) vs 'scale_out' (Method B)
        """
        data_file = os.path.join(PARENT_DIR, f"{ticker}_{self.target_date}.json")
        if not os.path.exists(data_file):
            return []

        # Strategy parameters
        tactical = self.levels_cache.get(ticker, {}).get("human_tactical", {})
        breakout_val = tactical.get("breakout_trigger")
        tactical_res = tactical.get("tactical_resistance", [])
        if breakout_val is None and isinstance(tactical_res, list) and len(tactical_res) > 0:
            breakout_val = float(tactical_res[0])
            
        reversal_zone = tactical.get("reversal_zone")
        low_z, high_z = None, None
        if isinstance(reversal_zone, list) and len(reversal_zone) > 0:
            if len(reversal_zone) >= 2:
                low_z, high_z = min(reversal_zone), max(reversal_zone)
            elif len(reversal_zone) == 1:
                center = float(reversal_zone[0])
                low_z, high_z = center - self.range_safeguard, center + self.range_safeguard

        # Loop caches
        rolling_prices = []
        current_bar_state = {}
        sidekick_signals = {}
        trade_history = []
        
        # Virtual portfolio settings
        in_trade = False
        strategy_active = None
        entry_price = 0.0
        
        # Multi-Contract Exiting Trackers
        scale_out_hit = False
        scale_out_target = 0.0
        stop_loss_level = 0.0
        take_profit_level = 0.0
        
        tick_idx = 0
        cooldown_until_idx = 0
        MIN_COOLDOWN_TICKS = 600
        last_conviction = None
        prev_price = None

        with open(data_file, 'rb') as f:
            parser = ijson.items(f, 'item')
            for tick in parser:
                price = float(tick.get('price'))
                vol = float(tick.get('size', 0))
                tick_time_str = tick.get('time')

                # --- 1.5% SPIKE FILTER ---
                if len(rolling_prices) >= 5:
                    prices_sorted = sorted(rolling_prices)
                    median_price = prices_sorted[len(prices_sorted) // 2]
                    deviation = abs(price - median_price) / median_price
                    if deviation > 0.015:
                        continue
                rolling_prices.append(price)
                if len(rolling_prices) > 10:
                    rolling_prices.pop(0)

                tick_idx += 1

                # --- SENTRY SIDEKICK 1-MINUTE OHLCV AGGREGATOR ---
                if tick_time_str and len(tick_time_str) >= 16:
                    minute_key = tick_time_str[:16]
                    if ticker not in current_bar_state:
                        current_bar_state[ticker] = {"minute": minute_key, "close": price, "volume": 0.0, "prev_close": price}
                    
                    if current_bar_state[ticker]["minute"] != minute_key:
                        completed = current_bar_state[ticker]
                        prev_v = completed["volume"]
                        # Check RVOL
                        if prev_v > 0 and (completed["volume"] / prev_v) >= 2.5:
                            wave_distance = completed["close"] - completed["prev_close"]
                            if wave_distance >= self.range_safeguard:
                                fib_entry = completed["close"] - (0.382 * wave_distance)
                                sidekick_signals[ticker] = {
                                    "entry_limit": round(fib_entry, 2),
                                    "wave": wave_distance,
                                    "active": True
                                }
                        current_bar_state[ticker] = {"minute": minute_key, "close": price, "volume": 0.0, "prev_close": completed["close"]}
                    
                    current_bar_state[ticker]["close"] = price
                    current_bar_state[ticker]["volume"] += vol

                if prev_price is None:
                    prev_price = price

                conditions = tick.get('conditions', tick.get('c', []))
                if not conditions: conditions = ["@"]

                try:
                    conv = calculate_trade_conviction(ticker, price, "LONG", vol, conditions=conditions)
                except Exception:
                    conv = {"conviction": "LOW"}
                curr_conv = conv.get("conviction")

                # --- EVALUATE POSITION EXITS ---
                if in_trade:
                    if method == "standard":
                        # METHOD A: Standard All-or-Nothing Exit
                        if price <= stop_loss_level:
                            net_pnl = -150.0 if strategy_active == "SIDEKICK_MICRO_SCALP" else -abs(500.0 * ((entry_price - price) / entry_price) * 10.0)
                            trade_history.append({"profit": net_pnl, "win": False})
                            in_trade = False
                            cooldown_until_idx = tick_idx + MIN_COOLDOWN_TICKS
                        elif price >= take_profit_level:
                            net_pnl = 5 * ((price - entry_price) * 0.50) * 100.0 if strategy_active == "SIDEKICK_MICRO_SCALP" else 500.0 * ((price - entry_price) / entry_price) * 10.0
                            trade_history.append({"profit": net_pnl, "win": True})
                            in_trade = False
                            cooldown_until_idx = tick_idx + MIN_COOLDOWN_TICKS
                    
                    else:
                        # METHOD B: Multicontract Scale-Out Exit
                        if not scale_out_hit:
                            # Still holding standard 5 contracts
                            if price <= stop_loss_level:
                                # Hit standard initial stop loss
                                net_pnl = -150.0 if strategy_active == "SIDEKICK_MICRO_SCALP" else -abs(500.0 * ((entry_price - price) / entry_price) * 10.0)
                                trade_history.append({"profit": net_pnl, "win": False})
                                in_trade = False
                                cooldown_until_idx = tick_idx + MIN_COOLDOWN_TICKS
                            elif price >= scale_out_target:
                                # Lock in 60% (3 contracts)
                                scale_out_hit = True
                                # Stop Loss moves to Break-even
                                stop_loss_level = entry_price
                        else:
                            # Holding remaining 2 contracts with Break-even SL
                            if price <= stop_loss_level:
                                # Stopped out remaining 2 contracts at break-even
                                profit_core = 3 * ((scale_out_target - entry_price) * 0.50) * 100.0 if strategy_active == "SIDEKICK_MICRO_SCALP" else 300.0 * ((scale_out_target - entry_price) / entry_price) * 10.0
                                trade_history.append({"profit": profit_core, "win": True})
                                in_trade = False
                                cooldown_until_idx = tick_idx + MIN_COOLDOWN_TICKS
                            elif price >= take_profit_level:
                                # Clean sweep! Hit final extension target
                                profit_core = 3 * ((scale_out_target - entry_price) * 0.50) * 100.0 if strategy_active == "SIDEKICK_MICRO_SCALP" else 300.0 * ((scale_out_target - entry_price) / entry_price) * 10.0
                                profit_runner = 2 * ((take_profit_level - entry_price) * 0.50) * 100.0 if strategy_active == "SIDEKICK_MICRO_SCALP" else 200.0 * ((take_profit_level - entry_price) / entry_price) * 10.0
                                trade_history.append({"profit": profit_core + profit_runner, "win": True})
                                in_trade = False
                                cooldown_until_idx = tick_idx + MIN_COOLDOWN_TICKS

                # --- EVALUATE POSITION ENTRIES ---
                else:
                    sidekick = sidekick_signals.get(ticker)
                    is_sidekick_fill = False
                    if sidekick and sidekick.get("active"):
                        if price <= sidekick["entry_limit"]:
                            is_sidekick_fill = True
                            entry_price = sidekick["entry_limit"]
                            sidekick["active"] = False

                            # Calculate exit matrices based on methods
                            wave = sidekick["wave"]
                            take_profit_level = round(entry_price + (0.272 * wave), 2)
                            scale_out_target = round(entry_price + (0.12 * wave), 2)
                            stop_loss_level = round(entry_price - 0.60, 2)
                            
                            strategy_active = "SIDEKICK_MICRO_SCALP"

                    is_livebot_signal = (curr_conv == "HIGH" and last_conviction != "HIGH")
                    is_breakout_signal = breakout_val and (prev_price < breakout_val <= price)
                    is_reversal_signal = low_z and high_z and (low_z <= price <= high_z) and (vol >= 500)

                    if (is_sidekick_fill or is_livebot_signal or is_breakout_signal or is_reversal_signal):
                        if tick_idx < cooldown_until_idx:
                            last_conviction = curr_conv
                            prev_price = price
                            continue

                        if not is_sidekick_fill:
                            entry_price = price
                            try:
                                sl, tp, _ = calculate_exits(price)
                            except Exception:
                                sl, tp = price - 0.45, price + 1.15
                            
                            stop_loss_level = sl
                            take_profit_level = tp
                            scale_out_target = entry_price + (tp - entry_price) * 0.50 # conservative target is half of standard target
                            strategy_active = "LIVEBOT_HIGH" if is_livebot_signal else "BREAKOUT"

                        in_trade = True
                        scale_out_hit = False

                last_conviction = curr_conv
                prev_price = price

        return trade_history

    def generate_metrics(self, history):
        if not history:
            return {"profit": 0.0, "trades": 0, "win_rate": 0.0, "profit_factor": 0.0}
        
        wins = [t for t in history if t["profit"] > 0]
        losses = [t for t in history if t["profit"] <= 0]
        
        gross_wins = sum([t["profit"] for t in wins])
        gross_losses = abs(sum([t["profit"] for t in losses]))
        
        win_rate = (len(wins) / len(history)) * 100
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else gross_wins
        
        return {
            "profit": round(sum([t["profit"] for t in history]), 2),
            "trades": len(history),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2)
        }

    def execute_comparison(self):
        print("\n" + "="*70)
        print(f" HARM.AI // STRATEGY EXIT METHODOLOGY SCORECARD ")
        print("="*70)
        print(f"Target Session  : {self.target_date}")
        print("Analysis Focus  : Standard Targets vs. 60/40 Scale-Out Protocols")
        print("="*70 + "\n")

        print(f"{'Ticker':<8} | {'Method A (Standard)':<27} | {'Method B (Scale-Out)':<27}")
        print(f"{'-'*8} | {'-'*27} | {'─'*27}")

        totals_a = []
        totals_b = []

        for ticker in TICKERS:
            hist_a = self.run_backtest_pass(ticker, method="standard")
            hist_b = self.run_backtest_pass(ticker, method="scale_out")
            
            totals_a.extend(hist_a)
            totals_b.extend(hist_b)

            m_a = self.generate_metrics(hist_a)
            m_b = self.generate_metrics(hist_b)

            if m_a["trades"] == 0 and m_b["trades"] == 0:
                continue

            str_a = f"${m_a['profit']:+7.2f} ({m_a['win_rate']:>5.1f}% WR, {m_a['trades']}T)"
            str_b = f"${m_b['profit']:+7.2f} ({m_b['win_rate']:>5.1f}% WR, {m_b['trades']}T)"
            print(f"{ticker:<8} | {str_a:<27} | {str_b:<27}")

        overall_a = self.generate_metrics(totals_a)
        overall_b = self.generate_metrics(totals_b)

        print(f"{'-'*8} | {'─'*27} | {'─'*27}")
        str_overall_a = f"${overall_a['profit']:+7.2f} ({overall_a['win_rate']:>5.1f}% WR, {overall_a['trades']}T)"
        str_overall_b = f"${overall_b['profit']:+7.2f} ({overall_b['win_rate']:>5.1f}% WR, {overall_b['trades']}T)"
        print(f"{'OVERALL':<8} | {str_overall_a:<27} | {str_overall_b:<27}")
        print(f"{'Pr.Fact':<8} | {f'{overall_a['profit_factor']:.2f}x':<27} | {f'{overall_b['profit_factor']:.2f}x':<27}")
        print("="*70)
        
        # Scalability and Reliability Analysis Verdict
        print("\n" + "="*70)
        print(" RESEARCH FINDINGS & VERDICT")
        print("="*70)
        if overall_b["win_rate"] > overall_a["win_rate"]:
            print(f"• Reliability (Win Rate) : Method B wins! (+{overall_b['win_rate'] - overall_a['win_rate']:.2f}% higher consistency)")
        else:
            print(f"• Reliability (Win Rate) : Method A wins! ({overall_a['win_rate']:.2f}% WR vs {overall_b['win_rate']:.2f}% WR)")

        if overall_b["profit"] > overall_a["profit"]:
            print(f"• Net Profitability      : Method B wins! (+${overall_b['profit'] - overall_a['profit']:.2f} premium difference)")
        else:
            print(f"• Net Profitability      : Method A wins! (+${overall_a['profit'] - overall_b['profit']:.2f} premium difference)")

        factor_diff = overall_b["profit_factor"] - overall_a["profit_factor"]
        if factor_diff > 0:
            print(f"• Portfolio Scalability  : Method B wins! (+{factor_diff:.2f}x higher risk-adjusted return efficiency)")
        else:
            print(f"• Portfolio Scalability  : Method A wins! ({overall_a['profit_factor']:.2f}x vs {overall_b['profit_factor']:.2f}x)")
        print("="*70 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HARM.AI Exit Strategy Research Harness")
    parser.add_argument("--date", default="2026-07-07", help="Target evaluation session date")
    args = parser.parse_args()
    
    harness = EvaluationHarness(date=args.date)
    harness.execute_comparison()
