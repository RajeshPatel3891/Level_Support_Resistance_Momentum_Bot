import unittest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# Add src to python path
sys.path.append(os.path.abspath('.'))

from src.gex_exit_monitor import evaluate_gex_exits, MTTP_MAX_MINUTES


class TestGEXExitMonitorMTTP(unittest.TestCase):

    @patch('src.gex_exit_monitor.boto3.resource')
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.execute_tradier_close')
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    def test_mttp_time_expiration_rule(self, mock_sqlite_sync, mock_tradier_close, mock_quote, mock_boto_resource):
        """Rule 1: Trade open > 45 minutes forces MTTP_TIME_EXPIRED_45M exit."""
        print("\n🧪 [TEST 1] Testing MTTP Max Hold Time Expiration (>45m)...")
        
        # 1. Mock DynamoDB table response (Trade open 50 minutes ago)
        old_timestamp = (datetime.now() - timedelta(minutes=50)).strftime("%Y-%m-%d %H:%M:%S")
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [{
                'tenant_id': 'default',
                'trade_id': 'INTC_12345_INTC260807C00101000',
                'ticker': 'INTC',
                'occ_symbol': 'INTC260807C00101000',
                'entry_price': '1.90',
                'shares': '5.0',
                'timestamp': old_timestamp,
                'direction': 'CALL',
                'exit_status': 'ACTIVE'
            }]
        }
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_quote.return_value = {'bid': '1.85', 'last': '1.85'}
        mock_tradier_close.return_value = True

        # 2. Run evaluation
        evaluate_gex_exits()

        # 3. Assertions
        mock_tradier_close.assert_called_once_with('INTC260807C00101000', 'INTC', 5.0)
        mock_table.update_item.assert_called_once()
        
        # Verify exit reason in update call
        update_args = mock_table.update_item.call_args[1]
        self.assertEqual(update_args['ExpressionAttributeValues'][':status'], f"MTTP_TIME_EXPIRED_{MTTP_MAX_MINUTES}M")
        mock_sqlite_sync.assert_called_once()
        print("  [✓] PASSED: Time expiration triggered exit and updated DynamoDB + SQLite correctly.")

    @patch('src.gex_exit_monitor.boto3.resource')
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.execute_tradier_close')
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    def test_stop_loss_trigger_rule(self, mock_sqlite_sync, mock_tradier_close, mock_quote, mock_boto_resource):
        """Rule 2: Trade drawdown <= -20% forces STOP_LOSS_20PCT exit."""
        print("\n🧪 [TEST 2] Testing Hard Stop Loss Trigger (-20%)...")
        
        # Trade open 10m ago (Entry $2.00, Current $1.50 -> -25% PnL)
        recent_timestamp = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [{
                'tenant_id': 'default',
                'trade_id': 'NVDA_12345_NVDA260807C00220000',
                'ticker': 'NVDA',
                'occ_symbol': 'NVDA260807C00220000',
                'entry_price': '2.00',
                'shares': '1.0',
                'timestamp': recent_timestamp,
                'direction': 'CALL',
                'exit_status': 'ACTIVE'
            }]
        }
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_quote.return_value = {'bid': '1.50', 'last': '1.50'}
        mock_tradier_close.return_value = True

        evaluate_gex_exits()

        mock_tradier_close.assert_called_once_with('NVDA260807C00220000', 'NVDA', 1.0)
        update_args = mock_table.update_item.call_args[1]
        self.assertEqual(update_args['ExpressionAttributeValues'][':status'], "STOP_LOSS_20PCT")
        print("  [✓] PASSED: -25% drawdown correctly triggered STOP_LOSS_20PCT exit.")

    @patch('src.gex_exit_monitor.boto3.resource')
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.execute_tradier_close')
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    def test_take_profit_trigger_rule(self, mock_sqlite_sync, mock_tradier_close, mock_quote, mock_boto_resource):
        """Rule 3: Trade profit >= +50% forces TAKE_PROFIT_50PCT exit."""
        print("\n🧪 [TEST 3] Testing Take Profit Target (+50%)...")
        
        # Trade open 15m ago (Entry $2.00, Current $3.10 -> +55% PnL)
        recent_timestamp = (datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [{
                'tenant_id': 'default',
                'trade_id': 'PLTR_12345_PLTR260807C00155000',
                'ticker': 'PLTR',
                'occ_symbol': 'PLTR260807C00155000',
                'entry_price': '2.00',
                'shares': '2.0',
                'timestamp': recent_timestamp,
                'direction': 'CALL',
                'exit_status': 'ACTIVE'
            }]
        }
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_quote.return_value = {'bid': '3.10', 'last': '3.10'}
        mock_tradier_close.return_value = True

        evaluate_gex_exits()

        mock_tradier_close.assert_called_once_with('PLTR260807C00155000', 'PLTR', 2.0)
        update_args = mock_table.update_item.call_args[1]
        self.assertEqual(update_args['ExpressionAttributeValues'][':status'], "TAKE_PROFIT_50PCT")
        print("  [✓] PASSED: +55% gain correctly triggered TAKE_PROFIT_50PCT exit.")

    @patch('src.gex_exit_monitor.boto3.resource')
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.execute_tradier_close')
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    def test_normal_hold_state(self, mock_sqlite_sync, mock_tradier_close, mock_quote, mock_boto_resource):
        """Rule 4: Normal trade within limits (15m in trade, +10% PnL) remains ACTIVE."""
        print("\n🧪 [TEST 4] Testing Normal Active Hold State...")
        
        recent_timestamp = (datetime.now() - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [{
                'tenant_id': 'default',
                'trade_id': 'SOFI_12345_SOFI260807C00017000',
                'ticker': 'SOFI',
                'occ_symbol': 'SOFI260807C00017000',
                'entry_price': '0.50',
                'shares': '1.0',
                'timestamp': recent_timestamp,
                'direction': 'CALL',
                'exit_status': 'ACTIVE'
            }]
        }
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_quote.return_value = {'bid': '0.55', 'last': '0.55'}  # +10% PnL

        evaluate_gex_exits()

        # Verify no close or update was dispatched
        mock_tradier_close.assert_not_called()
        mock_table.update_item.assert_not_called()
        mock_sqlite_sync.assert_not_called()
        print("  [✓] PASSED: Normal trade correctly remained ACTIVE without triggering exit.")


if __name__ == '__main__':
    print("=" * 65)
    print("🔬 RUNNING MTTP ENGINE UNIT TESTS")
    print("=" * 65)
    unittest.main(verbosity=1)
