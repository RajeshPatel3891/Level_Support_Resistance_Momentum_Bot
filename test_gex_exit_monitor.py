import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import os

from src.gex_exit_monitor import evaluate_gex_exits, MTTP_MAX_MINUTES

@patch.dict(os.environ, {'ACTIVE_TICKERS': ''})
class TestGEXExitMonitorMTTP(unittest.TestCase):

    @patch('src.gex_exit_monitor.is_regular_trading_hours', return_value=True)
    @patch('src.gex_exit_monitor.boto3.resource')
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    def test_mttp_time_expiration_rule(self, mock_sqlite_sync, mock_tradier_close, mock_quote, mock_boto_resource, mock_hours):
        """Rule 1: Trade open > 45 minutes forces MTTP_TIME_EXPIRED_45M exit."""
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
        mock_quote.return_value = (1.90, 'https://api.tradier.com/v1')

        evaluate_gex_exits()

        mock_tradier_close.assert_called_once_with('INTC260807C00101000', 'INTC', 4, 'https://api.tradier.com/v1')

    @patch('src.gex_exit_monitor.is_regular_trading_hours', return_value=True)
    @patch('src.gex_exit_monitor.boto3.resource')
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    def test_stop_loss_trigger_rule(self, mock_sqlite_sync, mock_tradier_close, mock_quote, mock_boto_resource, mock_hours):
        """Rule 2: Trade drawdown <= -20% forces STOP_LOSS_20PCT exit."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [{
                'tenant_id': 'default',
                'trade_id': 'NVDA_12345_NVDA260807C00220000',
                'ticker': 'NVDA',
                'occ_symbol': 'NVDA260807C00220000',
                'entry_price': '2.00',
                'shares': '1.0',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'direction': 'CALL',
                'exit_status': 'ACTIVE'
            }]
        }
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_quote.return_value = (1.50, 'https://api.tradier.com/v1')

        evaluate_gex_exits()

        mock_tradier_close.assert_called_once_with('NVDA260807C00220000', 'NVDA', 1, 'https://api.tradier.com/v1')

    @patch('src.gex_exit_monitor.is_regular_trading_hours', return_value=True)
    @patch('src.gex_exit_monitor.boto3.resource')
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    def test_take_profit_trigger_rule(self, mock_sqlite_sync, mock_tradier_close, mock_quote, mock_boto_resource, mock_hours):
        """Rule 3: Trade profit >= +50% forces TAKE_PROFIT_50PCT exit."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [{
                'tenant_id': 'default',
                'trade_id': 'PLTR_12345_PLTR260807C00155000',
                'ticker': 'PLTR',
                'occ_symbol': 'PLTR260807C00155000',
                'entry_price': '1.00',
                'shares': '1.0',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'direction': 'CALL',
                'exit_status': 'ACTIVE'
            }]
        }
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_quote.return_value = (1.55, 'https://api.tradier.com/v1')

        evaluate_gex_exits()

        mock_tradier_close.assert_called_once_with('PLTR260807C00155000', 'PLTR', 1, 'https://api.tradier.com/v1')

    @patch('src.gex_exit_monitor.is_regular_trading_hours', return_value=True)
    @patch('src.gex_exit_monitor.boto3.resource')
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.execute_tradier_close')
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    def test_normal_hold_state(self, mock_sqlite_sync, mock_tradier_close, mock_quote, mock_boto_resource, mock_hours):
        """Rule 4: Normal trade within limits remains ACTIVE without closing."""
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            'Items': [{
                'tenant_id': 'default',
                'trade_id': 'SOFI_12345_SOFI260807C00017000',
                'ticker': 'SOFI',
                'occ_symbol': 'SOFI260807C00017000',
                'entry_price': '0.50',
                'shares': '1.0',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'direction': 'CALL',
                'exit_status': 'ACTIVE',
                'min_pnl_seen': '5.0'
            }]
        }
        mock_boto_resource.return_value.Table.return_value = mock_table
        mock_quote.return_value = (0.55, 'https://api.tradier.com/v1')

        evaluate_gex_exits()

        mock_tradier_close.assert_not_called()

if __name__ == '__main__':
    unittest.main()
