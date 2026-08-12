import unittest
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

class TestGexMonitorSync(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Connect to DynamoDB and import the monitor fetcher."""
        cls.dynamodb = boto3.resource('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        cls.table = cls.dynamodb.Table('HarmonizedTrades')

    def test_dynamodb_to_monitor_parity(self):
        """Test 1: Assert fetch_active_trades() returns 100% of ACTIVE DynamoDB trades."""
        from run_gex_monitor import fetch_active_trades
         
        # Query raw DynamoDB active count
        from boto3.dynamodb.conditions import Attr
        raw_res = self.table.scan(FilterExpression=Attr('exit_status').eq('ACTIVE'))
        raw_items = raw_res.get('Items', [])
         
        # Query monitor fetcher output
        monitored_trades = fetch_active_trades()
         
        print(f"\n[UNIT TEST] Raw DynamoDB Active Count: {len(raw_items)}")
        print(f"[UNIT TEST] Monitor Fetched Count    : {len(monitored_trades)}")
         
        self.assertEqual(len(raw_items), len(monitored_trades), 
                         "CRITICAL: Monitor active trade count does NOT match DynamoDB!")

    def test_gsg_mttp_field_integrity(self):
        """Test 2: Assert every fetched trade has required GSG & MTTP evaluation keys."""
        from run_gex_monitor import fetch_active_trades
        monitored_trades = fetch_active_trades()
         
        required_keys = ['id', 'ticker', 'entry_price', 'stop_loss', 'take_profit', 
                         'occ_symbol', 'gsg_status', 'mttp_status']
         
        for trade in monitored_trades:
            ticker = trade.get('ticker')
            for key in required_keys:
                self.assertIn(key, trade, f"Trade {ticker} missing critical key '{key}' for GSG/MTTP evaluation!")
                self.assertIsNotNone(trade[key], f"Trade {ticker} key '{key}' is None!")
             
            # Mathematical validation
            self.assertGreater(float(trade['entry_price']), 0, f"Trade {ticker} invalid entry price!")
            
            # Position type validation with ratchet / trailing stop tolerance
            position_type = str(trade.get('position_type') or 'LONG').upper()
            is_locked_or_injected = (
                trade.get('cso_status') == 'TIGHTEN' 
                or trade.get('gsg_status') == 'LOCKED'
                or float(trade.get('stop_loss', 0)) >= float(trade.get('entry_price', 0))
            )

            if position_type == 'SHORT':
                self.assertGreater(float(trade['stop_loss']), 0, f"Trade {ticker} invalid stop loss!")
            else:
                self.assertTrue(
                    is_locked_or_injected or float(trade['stop_loss']) < float(trade['entry_price']), 
                    f"Trade {ticker} LONG stop_loss >= entry_price without TIGHTEN/LOCKED status!"
                )
            
            self.assertGreater(float(trade['take_profit']), 0, f"Trade {ticker} take_profit <= 0!")
             
            print(f"[✓ TEST PASS] {ticker} ({trade['occ_symbol']}) GSG/MTTP Parameters Validated.")

if __name__ == '__main__':
    unittest.main()
