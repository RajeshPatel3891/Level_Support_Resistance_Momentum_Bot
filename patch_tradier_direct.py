import re

fname = 'src/generate_dashboard_data.py'

tradier_direct_code = '''
def get_tradier_direct_telemetry():
    """Polls Tradier account endpoints directly as ground truth for active and closed positions."""
    import os, requests
    
    base_url = os.getenv('TRADIER_BASE_URL', 'https://api.tradier.com/v1')
    account_id = os.getenv('TRADIER_ACCOUNT_ID', '')
    token = os.getenv('TRADIER_TOKEN', '')
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }
    
    # 1. Fetch Realized Gain/Loss directly from Tradier
    realized_pnl = 0.0
    try:
        gl_resp = requests.get(f"{base_url}/accounts/{account_id}/gainloss", headers=headers, timeout=5)
        if gl_resp.status_code == 200:
            gl_data = gl_resp.json().get('gainloss', {})
            positions = gl_data.get('closed_position', [])
            if isinstance(positions, dict):
                positions = [positions]
            realized_pnl = sum(float(p.get('gain_loss', 0.0)) for p in positions)
    except Exception as e:
        print(f"[!] Warning: Could not fetch direct Tradier gainloss: {e}")
        
    return round(realized_pnl, 2)
'''

with open(fname, 'r') as f:
    content = f.read()

if 'get_tradier_direct_telemetry' not in content:
    content = tradier_direct_code + '\n' + content
    with open(fname, 'w') as f:
        f.write(content)
    print("[✓ PATCHED] Added direct Tradier ground-truth polling to generate_dashboard_data.py")
else:
    print("[!] Direct Tradier polling already present in script.")
