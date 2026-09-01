#!/usr/bin/env python3
"""
HARM.AI // LOCAL REAL-TIME DYNAMIC STOP EXIT SIMULATOR
===============================================================================
Emulates a real-time market data stream (replacing AWS Kinesis) using a Python 
asyncio Queue. Streams tick-by-tick option quotes to demonstrate how the dynamic 
stop loss ladder ratchets up and triggers exits.
"""

import asyncio
import random
import time
from datetime import datetime

class TickStreamSimulator:
    def __init__(self, ticker: str, entry_price: float):
        self.ticker = ticker
        self.entry_price = entry_price
        self.queue = asyncio.Queue()
        self.peak_price = entry_price
        self.stored_stop = round(entry_price * 0.80, 2)  # -20% initial stop
        self.is_active = True

    async def tick_producer(self):
        """Generates realistic tick-by-tick mark fluctuations."""
        current_price = self.entry_price
        step = 0

        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 [STREAM PRODUCER] Initialized tick stream for {self.ticker} @ Entry: ${self.entry_price:.2f}")
        
        while self.is_active and step < 30:
            await asyncio.sleep(0.5)  # Stream a tick every 500ms
            step += 1

            # Simulate price movement: initial push up (+12%), pullback, then breakdown
            if step <= 8:
                change = random.uniform(0.01, 0.03)  # Rising momentum
            elif step <= 15:
                change = random.uniform(-0.01, 0.02) # High volatility peak
            else:
                change = random.uniform(-0.03, -0.01) # Sharp pullback

            current_price = max(0.01, round(current_price * (1.0 + change), 2))
            bid = round(current_price * 0.98, 2)
            ask = round(current_price * 1.02, 2)

            tick_event = {
                "step": step,
                "ticker": self.ticker,
                "mark": current_price,
                "bid": bid,
                "ask": ask,
                "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3]
            }

            await self.queue.put(tick_event)

    async def exit_monitor_consumer(self):
        """Consumes real-time ticks and executes dynamic stop loss logic."""
        while self.is_active:
            tick = await self.queue.get()
            step = tick["step"]
            mark = tick["mark"]
            bid = tick["bid"]
            ask = tick["ask"]

            pnl_pct = ((mark - self.entry_price) / self.entry_price) * 100.0
            
            # Update peak price
            if mark > self.peak_price:
                self.peak_price = mark

            peak_pnl_pct = ((self.peak_price - self.entry_price) / self.entry_price) * 100.0

            # --- DYNAMIC STOP LOSS LADDER ENGINE ---
            previous_stop = self.stored_stop
            
            if peak_pnl_pct >= 35.0:
                self.stored_stop = max(self.stored_stop, round(self.entry_price * (1.0 + (peak_pnl_pct - 8.0) / 100.0), 2))
            elif peak_pnl_pct >= 20.0:
                self.stored_stop = max(self.stored_stop, round(self.entry_price * (1.0 + (peak_pnl_pct - 6.0) / 100.0), 2))
            elif peak_pnl_pct >= 5.0:  # Early +5% Dynamic Breakeven Floor
                self.stored_stop = max(self.stored_stop, round(self.entry_price * 1.01, 2))

            stop_tightened = self.stored_stop > previous_stop
            status_tag = "⚡ STOP TIGHTENED" if stop_tightened else "HOLDING"

            print(f"[{tick['timestamp']}] [TICK #{step:02d}] Mark: ${mark:.2f} ({pnl_pct:+.1f}%) | Peak: ${self.peak_price:.2f} (+{peak_pnl_pct:.1f}%) | Active Stop: ${self.stored_stop:.2f} | [{status_tag}]")

            # --- CHECK EXIT CONDITIONS ---
            if mark <= self.stored_stop:
                print("=" * 90)
                if self.stored_stop > self.entry_price:
                    print(f"🟢 [GREEN-STAY-GREEN EXIT TRIGGERED] Mark ${mark:.2f} crossed dynamic stop ${self.stored_stop:.2f}!")
                    print(f"   Realized Profit: +${(self.stored_stop - self.entry_price) * 100.0:.2f} per contract (+{((self.stored_stop - self.entry_price)/self.entry_price)*100:.1f}%)")
                else:
                    print(f"🔴 [STOP LOSS TRIGGERED] Mark ${mark:.2f} hit stop loss floor ${self.stored_stop:.2f}!")
                print("=" * 90)
                self.is_active = False

            self.queue.task_done()

async def run_simulation():
    simulator = TickStreamSimulator(ticker="NVDA", entry_price=2.00)
    print("=" * 90)
    print("🧪 HARM.AI // REAL-TIME DYNAMIC STOP LOSS STREAM SIMULATOR")
    print("=" * 90)
    await asyncio.gather(
        simulator.tick_producer(),
        simulator.exit_monitor_consumer()
    )

if __name__ == "__main__":
    asyncio.run(run_simulation())
