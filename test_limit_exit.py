from src.HarmonizedDispatch import force_exit_all
import os

# Test with a specific limit price (e.g., 750.50)
# This will print the exit trigger and attempt to send the order
print("--- Testing Limit Exit Logic ---")
print(force_exit_all("SPY", limit_price=750.50))
