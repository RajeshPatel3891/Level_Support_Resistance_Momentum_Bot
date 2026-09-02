import requests, time

TICKS = [
    # (bid, ask, note)
    (0.53, 0.55, "Dip on entry (-$1.00)"),
    (0.54, 0.56, "Breakeven return ($0.00)"),
    (0.56, 0.58, "Moving green (+$2.00 / +3.7%)"),
    (0.58, 0.60, "Arming green_stay_green (+$4.00 / +7.4%)"),
    (0.57, 0.59, "Pullback check - GSG should hold breakeven+1c"),
    (0.60, 0.62, "Extension push (+$6.00 / +11.1%)"),
    (0.62, 0.65, "Target zone hit (+$8.00 / +14.8%)")
]

print("[*] Streaming simulated tick progression for NKE260904P00080000...")
for bid, ask, note in TICKS:
    payload = {"symbol": "NKE260904P00080000", "bid": bid, "ask": ask, "last": bid}
    requests.post("http://localhost:8000/mock/update_quote", json=payload)
    print(f" -> Pushed tick: Bid ${bid:.2f} / Ask ${ask:.2f} | {note}")
    time.sleep(3)
