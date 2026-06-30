from LiveBot import calculate_exits
price = 730.00
sl, tp1, tp2 = calculate_exits(price)
print(f"Testing Exit Logic for ${price}:")
print(f"SL: {sl:.2f} | TP1: {tp1:.2f} | TP2: {tp2:.2f}")
