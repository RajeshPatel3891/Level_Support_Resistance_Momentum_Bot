import os
import re
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from playwright.sync_api import sync_playwright

try:
    from level_synthesizer import synthesize_levels
except ImportError:
    from src.level_synthesizer import synthesize_levels

EXECUTION_ENV = os.getenv("EXECUTION_ENV", "DEVELOPMENT")
TENANT_ID = os.getenv("TENANT_ID", "DEFAULT_TENANT")

MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), 
    "trading_levels_tradealgo.json"
)
COOKIE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cookies.json')

def extract_ticker_block(ticker: str, all_tickers: list, full_text: str) -> str:
    other_tickers = [t for t in all_tickers if t != ticker]
    other_pattern = r"(?:\n|\b)(?:" + "|".join(other_tickers) + r")(?::|\b|\n|\s*-)"
    ticker_pattern = rf"(?:^|\n|\b){ticker}(?::|\b|\n|\s*-)(.*?)(?={other_pattern}|\Z)"
    match = re.search(ticker_pattern, full_text, re.DOTALL | re.IGNORECASE)
    return match.group(1) if match else full_text

def parse_single_ticker_data(ticker: str, all_tickers: list, full_text: str) -> dict:
    block = extract_ticker_block(ticker, all_tickers, full_text)
    data = {}

    spot_match = re.search(r'(?:Last close|Price|Spot|Current)[^0-9]*\$?([0-9]+\.[0-9]+)', block, re.IGNORECASE)
    if spot_match:
        data["spot"] = float(spot_match.group(1))

    low_match = re.search(r'(?:Intraday low|Low|Support|S1|Sup)[^0-9]*~?\$?([0-9]+\.[0-9]+)', block, re.IGNORECASE)
    high_match = re.search(r'(?:Intraday high|High|Resistance|R1|Res)[^0-9]*~?\$?([0-9]+\.[0-9]+)', block, re.IGNORECASE)
    vwap_match = re.search(r'(?:VWAP)[^0-9]*~?\$?([0-9]+\.[0-9]+)', block, re.IGNORECASE)

    if low_match:
        data["intraday_low"] = float(low_match.group(1))
    if high_match:
        data["intraday_high"] = float(high_match.group(1))
    if vwap_match:
        data["vwap"] = float(vwap_match.group(1))

    if "spot" not in data:
        prices = re.findall(r'\$([0-9]+\.[0-9]+)', block)
        valid_prices = [float(p) for p in prices if float(p) > 2.0]
        if valid_prices:
            data["spot"] = valid_prices[0]

    return ticker, data

def parse_all_tickers_parallel(tickers: list, full_text: str) -> dict:
    parsed_results = {}
    with ThreadPoolExecutor(max_workers=min(32, len(tickers))) as executor:
        futures = [executor.submit(parse_single_ticker_data, ticker, tickers, full_text) for ticker in tickers]
        for f in futures:
            try:
                ticker, res = f.result()
                if res and "spot" in res:
                    parsed_results[ticker] = res
            except Exception as e:
                pass
    return parsed_results

def harvest_ticker_batch(tickers_to_process):
    if not os.path.exists(MANIFEST_PATH):
        print(f"[-] Manifest not found at {MANIFEST_PATH}")
        return tickers_to_process

    with open(MANIFEST_PATH, "r") as f:
        manifest = json.load(f)

    is_headless = True
    batch_prompt = (
        "What are key " + ", ".join(tickers_to_process) + 
        " intraday support and resistance levels and VWAP today?"
    )

    full_response_text = ""

    with sync_playwright() as p:
        # Use persistent context pointing to local profile to preserve LocalStorage, session state, and auth tokens
        user_data_dir = os.path.expanduser("~/.tradealgo_playwright_profile")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=is_headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        page = context.pages[0] if context.pages else context.new_page()

        try:
            print(f"[*] Loading TradeAlgo dashboard for parallel batch sweep of {len(tickers_to_process)} tickers...")
            page.goto("https://dashboard.tradealgo.com/home/Intraday/Auto/Up", timeout=45000)
            page.wait_for_timeout(3000)

            print("[*] Waiting for TradeGPT element...")
            tradegpt_button = page.locator("text='TradeGPT'").first
            try:
                tradegpt_button.wait_for(state="visible", timeout=30000)
            except:
                # Fallback role locator if text locator fails in headless mode
                tradegpt_button = page.get_by_role("button", name=re.compile("TradeGPT", re.IGNORECASE)).first
                tradegpt_button.wait_for(state="visible", timeout=15000)
            tradegpt_button.click()
            page.wait_for_timeout(1500)

            input_selector = "textarea[placeholder*='Ask TradeGPT'], textarea[placeholder*='Ask']"
            page.wait_for_selector(input_selector, timeout=10000)
            page.click(input_selector)

            chat_selector = "div[class*='tradegpt'], div[class*='chat'], div[class*='modal']"
            initial_text = page.locator(chat_selector).last.inner_text() if page.locator(chat_selector).count() > 0 else ""
            initial_len = len(initial_text)

            print(f"[*] Submitting master batch prompt...")
            page.fill(input_selector, batch_prompt)
            page.press(input_selector, "Enter")

            try:
                page.wait_for_selector("text='Analyzing'", timeout=3000)
            except Exception:
                pass

            print("[*] Waiting for TradeGPT stream to complete...")
            try:
                page.wait_for_selector("text='Analyzing'", state="detached", timeout=45000)
            except Exception:
                pass

            try:
                page.wait_for_function(
                    f"""() => {{
                        const chatBox = document.querySelector("div[class*='tradegpt'], div[class*='chat'], div[class*='modal']");
                        if (!chatBox) return false;
                        return chatBox.innerText.length > {initial_len + 300};
                    }}""",
                    timeout=25000
                )
            except Exception:
                pass

            page.wait_for_timeout(2000)

            chat_elements = page.locator("div[class*='markdown'], div[class*='bot'], div[class*='answer'], div[class*='message'] p").all_text_contents()
            full_response_text = "\n".join([t for t in chat_elements if len(t.strip()) > 20 and not t.strip().startswith("What are key")])

            if not full_response_text:
                full_response_text = page.inner_text("body")[-4000:]

        except Exception as e:
            print(f"[-] Browser harvest error: {e}")
        finally:
            context.close()

    if not full_response_text:
        print("[-] Failed to capture response text from TradeGPT.")
        return tickers_to_process

    print(f"[*] Parsing batch response via parallel regex engine...")
    parsed_batch = parse_all_tickers_parallel(tickers_to_process, full_response_text)

    updated_count = 0
    failed_tickers = []

    for ticker in tickers_to_process:
        if ticker in parsed_batch:
            data = parsed_batch[ticker]
            spot = data["spot"]
            manifest[ticker]["spot"] = spot
            manifest[ticker]["price"] = spot
            manifest[ticker]["last_price"] = spot
            manifest[ticker]["spot_price"] = spot
            manifest[ticker]["vwap"] = data.get("vwap", spot)

            zone_pct = manifest[ticker].get("zone_pct", 0.003)
            manifest[ticker]["call_target"] = round(spot * (1 + zone_pct), 2)
            manifest[ticker]["put_target"] = round(spot * (1 - zone_pct), 2)
            manifest[ticker]["spot_target_call"] = manifest[ticker]["call_target"]
            manifest[ticker]["spot_target_put"] = manifest[ticker]["put_target"]

            if "intraday_low" in data:
                low = data["intraday_low"]
                manifest[ticker]["support_zone"] = [low, round(low * 1.005, 2)]
                manifest[ticker]["support_a"] = low
                manifest[ticker]["support_b"] = round(low * 1.005, 2)

            if "intraday_high" in data:
                high = data["intraday_high"]
                manifest[ticker]["resistance_zone"] = [round(high * 0.995, 2), high]
                manifest[ticker]["resistance_a"] = round(high * 0.995, 2)
                manifest[ticker]["resistance_b"] = high

            updated_count += 1
        else:
            failed_tickers.append(ticker)

    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=4)

    print(f"[✓] Successfully updated {updated_count}/{len(tickers_to_spec_if_needed := tickers_to_process)} tickers in manifest.")
    return failed_tickers

def run_daemon():
    print(f"[*] Starting TradeGPT Fast Parallel Harvester Daemon | Env: {EXECUTION_ENV} | Target: trading_levels_tradealgo.json")
    while True:
        if not os.path.exists(MANIFEST_PATH):
            print(f"[-] Manifest not found at {MANIFEST_PATH}. Waiting 60s...")
            time.sleep(60)
            continue

        with open(MANIFEST_PATH, "r") as f:
            manifest = json.load(f)
        tickers = list(manifest.keys())

        start_time = time.time()
        print(f"\n==========================================")
        print(f"[*] Beginning fast batch sweep for {len(tickers)} tickers at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"==========================================")

        failed = harvest_ticker_batch(tickers)

        if failed:
            print(f"\n[*] Running retry queue for skipped/unparsed tickers: {failed}")
            time.sleep(5)
            still_failed = harvest_ticker_batch(failed)
            if still_failed:
                print(f"[x] Skipped entirely for this cycle (retaining prior levels): {still_failed}")

        print(f"\n[*] Sweep finished. Invoking level_synthesizer to update unified trading_levels.json...")
        try:
            synthesize_levels()
            print(f"[✓] Level synthesis completed successfully.")
        except Exception as e:
            print(f"[-] Error executing level_synthesizer: {e}")

        elapsed = round(time.time() - start_time, 1)
        print(f"\n[⚡] Full batch cycle completed in {elapsed}s. Sleeping for 30 minutes...")
        time.sleep(1800)

if __name__ == "__main__":
    run_daemon()
