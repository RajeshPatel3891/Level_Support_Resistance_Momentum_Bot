import json
import time
import pandas as pd
import numpy as np
from src.LiveBot import calculate_trade_conviction, load_integrated_levels

def mock_stream():
    print("--- Starting Volume-Validated Mock Stream ---")
    master_data = load_integrated_levels()
    if not master_data: return

    # Mock DataFrame with high volume to pass the 1.2x check
    mock_df = pd.DataFrame({
        'Volume': [1000] * 19 + [2000]  # Avg is 1000, Current is 2000 (2.0x, PASSES)
    })

    test_ticks = [("SPY", 730.00, "LONG"), ("QQQ", 705.00, "SHORT")]
    
    for ticker, price, side in test_ticks:
        print(f"\n[STREAM TICK] {ticker} @ ${price:.2f} | Side: {side}")
        conv = calculate_trade_conviction(ticker, price, side, master_data, mock_df)
        print(f" -> Conviction: {conv['conviction']} | Action: {conv['action']} | Vol: {conv['volume_status']} | Notes: {conv['notes']}")

if __name__ == "__main__":
    mock_stream()
