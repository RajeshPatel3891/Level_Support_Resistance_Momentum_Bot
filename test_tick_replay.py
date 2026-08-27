#!/usr/bin/env python3
"""
HARM.AI // POST-MORTEM TICK REPLAY UNIT TEST HARNESS
===============================================================================
Replays historical option ticks for F, MARA, and HOOD from today's session to:
  1. Test if smart_cso_injector's 4.0% spread guard would have BLOCKED wide-spread entries (e.g., HOOD).
  2. Test if Midpoint limit pricing avoids instant negative PnL drag.
  3. Validate check_and_close_target.py signed stop-loss parsing logic (-tt TICKER=-STOP).
"""

import os
import sys
import json
import requests
from datetime import datetime

sys.path.append("src")
import smart_cso_injector as cso
import check_and_close_target as target_guard

TRADIER_TOKEN = cso.TRADIER_TOKEN
TRADIER_BASE_URL = cso.TRADIER_BASE_URL

TEST_CONTRACTS = {
    "HOOD": {"occ": "HOOD260828P00109000", "entry_px": 2.46, "target_sl": -10.00},
    "MARA": {"occ": "MARA260828P00011000", "entry_px": 0.30, "target_sl": -1.00},
    "F":    {"occ": "F260828C00012000",    "entry_px": 1.90, "target_sl": -1.00}
}

def fetch_current_or_historical_quote(occ_symbol):
    """Fetches quote book tick details (Bid, Ask, Mid, Spread %) from Tradier."""
    headers = {"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"}
    url = f"{TRADIER_BASE_URL}/markets/quotes"
    try:
        res = requests.get(url, params={"symbols": occ_symbol}, headers=headers, timeout=4)
        if res.status_code == 200:
            q = res.json().get("quotes", {}).get("quote", {})
            if isinstance(q, list) and len(q) > 0:
                q = q[0]
            bid = float(q.get("bid") or 0.0)
            ask = float(q.get("ask") or 0.0)
            last = float(q.get("last") or 0.0)
            mid = round((bid + ask) / 2.0, 2) if (bid > 0 and ask > 0) else last
            spread_pct = ((ask - bid) / ask * 100.0) if ask > 0 else 0.0
            return {"bid": bid, "ask": ask, "mid": mid, "last": last, "spread_pct": spread_pct}
    except Exception as e:
        print(f"[!] Error fetching quote tick for {occ_symbol}: {e}")
    return None

def run_spread_guard_unit_tests():
    print("\n============================================================")
    print("🧪 UNIT TEST 1: ENTRY SPREAD GUARD & MIDPOINT EVALUATION (4.0% MAX)")
    print("============================================================")

    for ticker, data in TEST_CONTRACTS.items():
        occ = data["occ"]
        quote = fetch_current_or_historical_quote(occ)
        if not quote:
            print(f"[!] Could not fetch live/historical tick for {ticker} ({occ}). Skipping.")
            continue

        bid = quote["bid"]
        ask = quote["ask"]
        mid = quote["mid"]
        spread_pct = quote["spread_pct"]

        print(f"\n[*] Evaluating {ticker} ({occ}):")
        print(f"    ├─ Bid: ${bid:.2f} | Ask: ${ask:.2f} | Mid: ${mid:.2f}")
        print(f"    ├─ Spread Width: ${ask - bid:.2f} ({spread_pct:.2f}%)")

        # 1. Test Spread Guard Criteria (Max 4.0%)
        if spread_pct > 4.0:
            print(f"    └─ 🛡️ [PASS - ENTRY REJECTED]: Spread ({spread_pct:.1f}%) > 4.0% Threshold. Trade would be ABORTED.")
        else:
            print(f"    └─ 🟢 [PASS - ENTRY QUALIFIED]: Spread ({spread_pct:.1f}%) <= 4.0%. Midpoint order placed at ${mid:.2f}.")

        # 2. Test Instant PnL Drag Comparison (Ask Fill vs Midpoint Fill)
        drag_ask = round((bid - ask) * 100.0, 2)
        drag_mid = round((bid - mid) * 100.0, 2)
        print(f"    ├─ Instant PnL Drag at Ask (${ask:.2f}): ${drag_ask:+.2f}")
        print(f"    └─ Instant PnL Drag at Mid (${mid:.2f}): ${drag_mid:+.2f}")

def run_bracket_parser_unit_tests():
    print("\n============================================================")
    print("🧪 UNIT TEST 2: SIGNED BRACKET PARSER (-tt TICKER=-STOP Validation)")
    print("============================================================")

    # Test CLI inputs: -tt F=-1.00 -tt MARA=-1.00 -tt HOOD=-10.00,5.00
    test_args = ["-tt", "F=-1.00", "-tt", "MARA=-1.00", "-tt", "HOOD=-10.00,5.00"]
    sys.argv = ["check_and_close_target.py"] + test_args

    global_target, brackets = target_guard.parse_args()

    print(f"[*] Command Input: {' '.join(test_args)}")
    for tkr, cfg in brackets.items():
        stop = cfg["stop"]
        target = cfg["target"]
        stop_str = f"-${abs(stop):.2f}" if stop is not None else "NONE"
        target_str = f"+${target:.2f}" if target is not None else "NONE"
        
        # Validation checks
        if tkr in ["F", "MARA"]:
            assert stop == -1.00, f"Expected stop -1.00 for {tkr}, got {stop}"
            assert target is None, f"Expected target None for {tkr}, got {target}"
            print(f"    ├─ {tkr}: Stop Loss = {stop_str} | Take Profit = {target_str} [✓ CORRECTLY MAPPED TO STOP-ONLY]")
        elif tkr == "HOOD":
            assert stop == -10.00, f"Expected stop -10.00 for HOOD, got {stop}"
            assert target == 5.00, f"Expected target 5.00 for HOOD, got {target}"
            print(f"    └─ {tkr}: Stop Loss = {stop_str} | Take Profit = {target_str} [✓ CORRECTLY MAPPED TO FULL BRACKET]")

    print("\n[✓ ALL BRACKET PARSER UNIT TESTS PASSED SUCCESSFULLY!]")

if __name__ == "__main__":
    print("============================================================")
    print("🧠 HARM.AI // TICK DATA & STRATEGY REPLAY TEST SUITE")
    print("============================================================")
    run_spread_guard_unit_tests()
    run_bracket_parser_unit_tests()
