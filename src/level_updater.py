import json
import os

MANIFEST_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'trading_levels.json')

def update_ticker_level(ticker: str, spot: float, support_low: float, support_high: float, res_low: float, res_high: float, call_target: float, put_target: float, vwap: float):
    """
    Safely injects or updates a ticker's battleground levels in trading_levels.json.
    """
    levels = {}
    if os.path.exists(MANIFEST_PATH):
        try:
            with open(MANIFEST_PATH, "r") as f:
                data = json.load(f)
                levels = data.get("levels", data) if isinstance(data, dict) else {}
        except Exception as e:
            print(f"[!] Error reading manifest: {e}")
            return

    ticker_upper = ticker.upper()
    
    # Preserve existing configuration metadata if ticker already exists
    existing_config = levels.get(ticker_upper, {
        "zone_pct": 0.002,
        "turn_ticks": 2,
        "mttp_minutes": 20,
        "beta": "ETF",
        "proximity_threshold": 0.0075,
        "gap_pct": 0.5,
        "execution_armed": True
    })

    existing_config.update({
        "spot": spot,
        "price": spot,
        "last_price": spot,
        "spot_price": spot,
        "vwap": vwap,
        "call_target": call_target,
        "put_target": put_target,
        "spot_target_call": call_target,
        "spot_target_put": put_target,
        "support_a": support_low,
        "support_b": support_high,
        "resistance_a": res_low,
        "resistance_b": res_high,
        "support_zone": [support_low, support_high],
        "resistance_zone": [res_low, res_high],
        "execution_armed": True
    })

    levels[ticker_upper] = existing_config

    # Write back clean JSON structure
    output_data = {"levels": levels} if "levels" in data or not isinstance(list(levels.keys()) and levels.get(list(levels.keys())[0]), dict) else levels
    
    with open(MANIFEST_PATH, "w") as f:
        json.dump(output_data, f, indent=2)
    
    print(f"[✓] Successfully updated manifest levels for {ticker_upper}! Support: [{support_low}, {support_high}] | Resistance: [{res_low}, {res_high}]")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Quick Level Injector Helper")
    parser.add_argument("--ticker", type=str, required=True, help="Ticker symbol (e.g. QQQ)")
    parser.add_argument("--spot", type=float, required=True, help="Current spot price")
    parser.add_argument("--sup-low", type=float, required=True, help="Support zone low")
    parser.add_argument("--sup-high", type=float, required=True, help="Support zone high")
    parser.add_argument("--res-low", type=float, required=True, help="Resistance zone low")
    parser.add_argument("--res-high", type=float, required=True, help="Resistance zone high")
    parser.add_argument("--call-target", type=float, required=True, help="Upside call target")
    parser.add_argument("--put-target", type=float, required=True, help="Downside put target")
    parser.add_argument("--vwap", type=float, required=True, help="Current intraday VWAP")
    
    args = parser.parse_args()
    update_ticker_level(
        args.ticker, args.spot, args.sup_low, args.sup_high, 
        args.res_low, args.res_high, args.call_target, args.put_target, args.vwap
    )
