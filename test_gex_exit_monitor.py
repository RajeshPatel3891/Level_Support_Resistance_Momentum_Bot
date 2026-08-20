#!/usr/bin/env python3
"""
HARM.AI // GEX EXIT MONITOR UNIT TEST SUITE
===============================================================================
Comprehensive unit tests covering all Chief Strategy Officer (CSO) exit scenarios:
  1. Dynamic Trailing Stop Loss Trigger (Ratcheted High-Water Mark)
  2. Hard Target Cap (+50% Single Contract)
  3a. CSO Early Momentum Cut (CALL: Option down -12% AND Stock Spot < Support)
  3b. CSO Noise Filter Hold (CALL: Option down -12% BUT Stock Spot >= Support)
  3c. CSO Early Momentum Cut (PUT: Option down -12% AND Stock Spot > Resistance)
  4. Hard Stop Loss / Dynamic Floor Breach (-20% Floor Hit)
  5. MTTP Time Expiration (>= 45 Mins during RTH)
  6. Multi-Contract Tranche Scaling (+50% / GEX Target with >1 Contract)
  7. Normal Active Hold State (No Exit Triggered)
  8. CSO Missing Level Fallback Cut (Option down -12% AND Support Level == 0.0)
"""

import os
import sys
import unittest
from datetime import datetime as dt
from unittest.mock import patch, MagicMock

# Ensure root import path
sys.path.extend(['.', 'src', '/app', '/app/src'])

from src import gex_exit_monitor


class TestGEXExitMonitorAllScenarios(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures, environment variables, and mocks before each pass."""
        os.environ["ACTIVE_TICKERS"] = "PLTR,IWM,HOOD,UBER,SOFI,F,AAL,CCL"
        self.sample_item_base = {
            'tenant_id': 'COMPANY_A',
            'trade_id': 'TEST_TRADE_123',
            'ticker': 'PLTR',
            'occ_symbol': 'PLTR260821C00175000',
            'entry_price': '2.00',
            'shares': '1',
            'timestamp': dt.now().strftime("%Y-%m-%d %H:%M:%S"),
            'direction': 'CALL',
            'peak_price': '2.00',
            'stop_loss': '1.60',
            'is_runner': False,
            'partial_pnl': '0.0',
            'min_pnl_seen': '0.0'
        }

    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    @patch('src.gex_exit_monitor.get_gex_target_info', return_value=(175.0, 180.0, 2.8))
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.boto3.resource')
    def test_scenario_1_dynamic_trailing_stop_triggered(
        self, mock_boto3, mock_get_quote, mock_gex_info, mock_sqlite_sync, mock_close
    ):
        """Scenario 1: Peak ratcheted to $2.50 (+25%), live price falls to $2.20, breaching stop ($2.30)."""
        item = self.sample_item_base.copy()
        item['peak_price'] = '2.50'
        item['stop_loss'] = '2.30'
        mock_get_quote.return_value = (2.20, "https://api.tradier.com/v1")

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [item]}
        mock_boto3.return_value.Table.return_value = mock_table

        gex_exit_monitor.evaluate_gex_exits()

        mock_close.assert_called_once()
        last_update = mock_table.update_item.call_args_list[-1]
        expr_vals = last_update.kwargs['ExpressionAttributeValues']
        self.assertTrue('DYNAMIC_TRAIL_STOP_TRIGGERED' in expr_vals[':status'])

    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    @patch('src.gex_exit_monitor.get_gex_target_info', return_value=(175.0, 180.0, 2.8))
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.boto3.resource')
    def test_scenario_2_take_profit_50pct(
        self, mock_boto3, mock_get_quote, mock_gex_info, mock_sqlite_sync, mock_close
    ):
        """Scenario 2: Single contract hits +50% profit mark ($3.00 on $2.00 entry)."""
        item = self.sample_item_base.copy()
        mock_get_quote.return_value = (3.00, "https://api.tradier.com/v1")

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [item]}
        mock_boto3.return_value.Table.return_value = mock_table

        gex_exit_monitor.evaluate_gex_exits()

        mock_close.assert_called_once()
        last_update = mock_table.update_item.call_args_list[-1]
        expr_vals = last_update.kwargs['ExpressionAttributeValues']
        self.assertEqual(expr_vals[':status'], 'TAKE_PROFIT_50PCT')

    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    @patch('src.gex_exit_monitor.get_gex_target_info', return_value=(172.0, 180.0, 4.4))  # Spot $172 < Support $180
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.boto3.resource')
    def test_scenario_3a_cso_early_momentum_cut_call(
        self, mock_boto3, mock_get_quote, mock_gex_info, mock_sqlite_sync, mock_close
    ):
        """Scenario 3a: CALL down -12% ($1.76) AND stock breaches support ($172 spot < $180 support)."""
        item = self.sample_item_base.copy()
        item['direction'] = 'CALL'
        mock_get_quote.return_value = (1.76, "https://api.tradier.com/v1")

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [item]}
        mock_boto3.return_value.Table.return_value = mock_table

        gex_exit_monitor.evaluate_gex_exits()

        mock_close.assert_called_once()
        last_update = mock_table.update_item.call_args_list[-1]
        expr_vals = last_update.kwargs['ExpressionAttributeValues']
        self.assertTrue('CSO_EARLY_MOMENTUM_CUT' in expr_vals[':status'])

    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.get_gex_target_info', return_value=(176.0, 175.0, 0.5))  # Spot $176 >= Support $175
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.boto3.resource')
    def test_scenario_3b_cso_noise_filter_hold_call(
        self, mock_boto3, mock_get_quote, mock_gex_info, mock_close
    ):
        """Scenario 3b: CALL mark down -12% ($1.76) BUT stock holds structure ($176 spot >= $175 support) -> NO EXIT."""
        item = self.sample_item_base.copy()
        item['direction'] = 'CALL'
        mock_get_quote.return_value = (1.76, "https://api.tradier.com/v1")

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [item]}
        mock_boto3.return_value.Table.return_value = mock_table

        gex_exit_monitor.evaluate_gex_exits()

        mock_close.assert_not_called()

    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    @patch('src.gex_exit_monitor.get_gex_target_info', return_value=(178.0, 170.0, -4.5))  # Spot $178 > Resistance $170
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.boto3.resource')
    def test_scenario_3c_cso_early_momentum_cut_put(
        self, mock_boto3, mock_get_quote, mock_gex_info, mock_sqlite_sync, mock_close
    ):
        """Scenario 3c: PUT down -12% ($1.76) AND stock breaches resistance ($178 spot > $170 resistance)."""
        item = self.sample_item_base.copy()
        item['direction'] = 'PUT'
        mock_get_quote.return_value = (1.76, "https://api.tradier.com/v1")

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [item]}
        mock_boto3.return_value.Table.return_value = mock_table

        gex_exit_monitor.evaluate_gex_exits()

        mock_close.assert_called_once()
        last_update = mock_table.update_item.call_args_list[-1]
        expr_vals = last_update.kwargs['ExpressionAttributeValues']
        self.assertTrue('CSO_EARLY_MOMENTUM_CUT' in expr_vals[':status'])

    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    @patch('src.gex_exit_monitor.get_gex_target_info', return_value=(175.0, 180.0, 2.8))
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.boto3.resource')
    def test_scenario_4_hard_stop_loss_20pct(
        self, mock_boto3, mock_get_quote, mock_gex_info, mock_sqlite_sync, mock_close
    ):
        """Scenario 4: Hard -20% stop loss breach ($1.58 on $2.00 entry)."""
        item = self.sample_item_base.copy()
        mock_get_quote.return_value = (1.58, "https://api.tradier.com/v1")

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [item]}
        mock_boto3.return_value.Table.return_value = mock_table

        gex_exit_monitor.evaluate_gex_exits()

        mock_close.assert_called_once()
        last_update = mock_table.update_item.call_args_list[-1]
        expr_vals = last_update.kwargs['ExpressionAttributeValues']
        self.assertTrue('DYNAMIC_TRAIL_STOP_TRIGGERED' in expr_vals[':status'] or 'STOP_LOSS_20PCT' in expr_vals[':status'])

    @patch('src.gex_exit_monitor.is_regular_trading_hours', return_value=True)
    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    @patch('src.gex_exit_monitor.get_gex_target_info', return_value=(175.0, 180.0, 2.8))
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.boto3.resource')
    def test_scenario_5_mttp_time_expiration(
        self, mock_boto3, mock_get_quote, mock_gex_info, mock_sqlite_sync, mock_close, mock_rth
    ):
        """Scenario 5: Position open > 45 minutes during RTH with no target/stop breach."""
        item = self.sample_item_base.copy()
        item['timestamp'] = '2026-08-19 12:00:00'
        mock_get_quote.return_value = (2.05, "https://api.tradier.com/v1")

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [item]}
        mock_boto3.return_value.Table.return_value = mock_table

        gex_exit_monitor.evaluate_gex_exits()

        mock_close.assert_called_once()
        last_update = mock_table.update_item.call_args_list[-1]
        expr_vals = last_update.kwargs['ExpressionAttributeValues']
        self.assertTrue('MTTP_TIME_EXPIRED' in expr_vals[':status'])

    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    @patch('src.gex_exit_monitor.get_gex_target_info', return_value=(175.0, 180.0, 2.8))
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.boto3.resource')
    def test_scenario_6_tranche_partial_scale_out(
        self, mock_boto3, mock_get_quote, mock_gex_info, mock_sqlite_sync, mock_close
    ):
        """Scenario 6: Multi-contract trade (2x) hits +50% target ($3.00). Scales 1x and leaves 1x RUNNER."""
        item = self.sample_item_base.copy()
        item['shares'] = '2'
        mock_get_quote.return_value = (3.00, "https://api.tradier.com/v1")

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [item]}
        mock_boto3.return_value.Table.return_value = mock_table

        gex_exit_monitor.evaluate_gex_exits()

        mock_close.assert_called_once_with('PLTR260821C00175000', 'PLTR', 1, "https://api.tradier.com/v1")
        last_update = mock_table.update_item.call_args_list[-1]
        expr_vals = last_update.kwargs['ExpressionAttributeValues']
        self.assertEqual(expr_vals[':sh'], '1')
        self.assertTrue(expr_vals[':r'])
        self.assertEqual(expr_vals[':cs'], 'SMART_CSO_RUNNER')

    @patch('src.gex_exit_monitor.execute_tradier_close')
    @patch('src.gex_exit_monitor.get_gex_target_info', return_value=(175.0, 180.0, 2.8))
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.boto3.resource')
    def test_scenario_7_normal_active_hold_state(
        self, mock_boto3, mock_get_quote, mock_gex_info, mock_close
    ):
        """Scenario 7: Position active within normal limits (+5% gain, recent timestamp). No exit triggered."""
        item = self.sample_item_base.copy()
        mock_get_quote.return_value = (2.10, "https://api.tradier.com/v1")

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [item]}
        mock_boto3.return_value.Table.return_value = mock_table

        gex_exit_monitor.evaluate_gex_exits()

        mock_close.assert_not_called()

    @patch('src.gex_exit_monitor.execute_tradier_close', return_value=True)
    @patch('src.gex_exit_monitor.sync_local_sqlite_exit')
    @patch('src.gex_exit_monitor.get_gex_target_info', return_value=(172.0, 0.0, 0.0))  # Missing support level (0.0)
    @patch('src.gex_exit_monitor.get_live_quote')
    @patch('src.gex_exit_monitor.boto3.resource')
    def test_scenario_8_cso_missing_level_fallback_cut(
        self, mock_boto3, mock_get_quote, mock_gex_info, mock_sqlite_sync, mock_close
    ):
        """Scenario 8: Option down -12% ($1.76) AND GEX level data missing (0.0 support) -> Caps loss at -12% fallback floor."""
        item = self.sample_item_base.copy()
        mock_get_quote.return_value = (1.76, "https://api.tradier.com/v1")  # -12.0% PnL

        mock_table = MagicMock()
        mock_table.scan.return_value = {'Items': [item]}
        mock_boto3.return_value.Table.return_value = mock_table

        gex_exit_monitor.evaluate_gex_exits()

        mock_close.assert_called_once()
        last_update = mock_table.update_item.call_args_list[-1]
        expr_vals = last_update.kwargs['ExpressionAttributeValues']
        self.assertTrue('CSO_MISSING_LEVEL_FALLBACK_CUT' in expr_vals[':status'])


if __name__ == '__main__':
    unittest.main()
