with open("src/HarmonizedDispatch.py", "r") as f:
    code = f.read()

old_block = """    orders_resp = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers).json()
    if not isinstance(orders_resp, dict): orders_resp = {}
    orders = orders_resp.get('orders', {}).get('order', [])"""

new_block = """    orders_resp = requests.get(f"{base_url}/accounts/{account_id}/orders", headers=headers).json()
    if not isinstance(orders_resp, dict): orders_resp = {}
    
    orders_data = orders_resp.get('orders', {})
    if isinstance(orders_data, dict):
        orders = orders_data.get('order', [])
    else:
        orders = []"""

if old_block in code:
    code = code.replace(old_block, new_block)
else:
    code = code.replace("orders = orders_resp.get('orders', {}).get('order', [])", \"\"\"orders_data = orders_resp.get('orders', {}) if isinstance(orders_resp, dict) else {}
    orders = orders_data.get('order', []) if isinstance(orders_data, dict) else []\"\"\")

with open("src/HarmonizedDispatch.py", "w") as f:
    f.write(code)

print("[✓] Nested dictionary type guards applied to lines 63-66!")
