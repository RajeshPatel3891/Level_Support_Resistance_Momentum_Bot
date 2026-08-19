import unittest
import os
import requests

class TestTradierLiveAuth(unittest.TestCase):

    @unittest.skipUnless(os.path.exists('.env.prod'), "Skipping live Tradier check: .env.prod not present on host")
    def test_prod_tradier_authentication_and_balances(self):
        """Integration: Verify live Tradier PROD credentials and balance endpoints."""
        env_vars = {}
        with open('.env.prod', 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    env_vars[key.strip()] = val.strip()

        api_url = env_vars.get('TRADIER_BASE_URL', 'https://api.tradier.com/v1')
        token = env_vars.get('TRADIER_TOKEN') or env_vars.get('TRADIER_ACCESS_TOKEN')
        account_id = env_vars.get('TRADIER_ACCOUNT_ID')

        self.assertIsNotNone(token, "TRADIER_TOKEN missing from .env.prod")
        self.assertIsNotNone(account_id, "TRADIER_ACCOUNT_ID missing from .env.prod")

        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json'
        }

        # 1. Profile / Auth Check
        res = requests.get(f'{api_url}/user/profile', headers=headers)
        self.assertEqual(res.status_code, 200, f"Tradier Auth Failed ({res.status_code}): {res.text}")

        # 2. Balances Check
        bal_res = requests.get(f'{api_url}/accounts/{account_id}/balances', headers=headers)
        self.assertEqual(bal_res.status_code, 200, f"Balance Fetch Failed ({bal_res.status_code}): {bal_res.text}")

if __name__ == '__main__':
    unittest.main()
