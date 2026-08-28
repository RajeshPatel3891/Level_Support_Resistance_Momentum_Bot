#!/usr/bin/env python3
"""
HARM.AI // DYNAMIC GEX & PROXIMITY TARGET GENERATOR
===============================================================================
Computes structured call/put targets and support/resistance zones based on 
live spot prices and beta tiers, enabling smart_cso_injector arming states.
"""

import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from src.level_loader import load_trading_levels, save_trading_levels

if os.path.exists(".env.prod"):
    load_dotenv(".env.prod", override=True)
else:
    load_dotenv(override=True)

def generate_targets():
    data = load_trading_levels(force_refresh=True)
    if not data:
        print("[!] No trading levels found to update.")
        return

    print("[*] Generating dynamic GEX targets and zones across matrix...")

    for ticker, val in data.items():
        if not isinstance(val, dict):
            continue

        spot = float(val.get("spot") or val.get("last_price") or 0.0)
        if spot <= 0:
            continue

        # Get beta/zone parameters or default to MID tier
        zone_pct = float(val.get("zone_pct", 0.003))

        # Dynamically set call and put targets based on zone spacing (GEX wall simulation)
        call_target = round(spot * (1.0 + (zone_pct * 1.5)), 2)
        put_target = round(spot * (1.0 - (zone_pct * 1.5)), 2)

        # Build structured support and resistance zones
        sup_zone = [round(put_target * (1.0 - zone_pct), 2), put_target]
        res_zone = [call_target, round(call_target * (1.0 + zone_pct), 2)]

        # Assign back to ticker payload
        val["call_target"] = call_target
        val["put_target"] = put_target
        val["spot_target_call"] = call_target
        val["spot_target_put"] = put_target
        val["support_zone"] = sup_zone
        val["resistance_zone"] = res_zone
        val["support_a"] = sup_zone[0]
        val["support_b"] = sup_zone[1]
        val["resistance_a"] = res_zone[0]
        val["resistance_b"] = res_zone[1]

    save_trading_levels(data)
    print("[✓] Dynamic GEX targets successfully generated, synced to S3, and written to disk!")

if __name__ == "__main__":
    generate_targets()
