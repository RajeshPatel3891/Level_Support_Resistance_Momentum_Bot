#!/usr/bin/env python3
"""
HARM.AI // ILLIQUID TRAP & EXECUTION SAFETY UNIT TEST SUITE (WITH FILL QUALITY SCORES)
===============================================================================
Validates:
1. smart_cso_injector: Pre-entry liquidity filtering (zero bid, wide spread, low OI/volume).
2. gex_exit_monitor: Stepped exit pricing calculations (midpoint vs bid fallback).
3. check_and_close_target: Realistic Bid-based PnL evaluation vs inflated Ask prices.
4. Fill Quality Scoring: Evaluates fill efficiency on a 0.0 to 10.0 scale.
"""

import unittest
from unittest.mock import patch, MagicMock

from src.smart_cso_injector import validate_option_liquidity
from src.gex_exit_monitor import execute_tradier_close_stepped
from check_and_close_target import scan_and_close_targets


def calculate_fill_quality_score(fill_price: float, bid: float, ask: float, side: str = "sell") -> float:
    """
    Calculates Fill Quality Score on a 0.0 to 10.0 scale.
    - 10.0 = Best possible fill (Bid on sell, Ask on buy).
    - 5.0  = Midpoint fill.
    - 0.0  = Worst possible fill (Ask on sell, Bid on buy).
    """
    if ask <= bid or fill_price <= 0:
        return 0.0
    
    mid = (bid + ask) / 2.0
    spread = ask - bid
    
    if side.lower() in ["sell", "sell_to_close"]:
        # Higher price is better for seller
        score = ((fill_price - bid) / spread) * 10.0
    else:
        # Lower price is better for buyer
        score = ((ask - fill_price) / spread) * 10.0
        
    return round(max(0.0, min(10.0, score)), 2)


class TestIlliquidTrapGuards(unittest.TestCase):

    # =========================================================================
    # TEST SET 1: PRE-ENTRY LIQUIDITY & VOLUME GUARDS (smart_cso_injector.py)
    # =========================================================================

    def test_zero_bid_trap_rejected(self):
        """Reject contracts with zero or $0.01 bid (RIVN-style penny trap)."""
        bad_quote = {"bid": 0.01, "ask": 0.50, "open_interest": 500, "volume": 100}
        valid, reason = validate_option_liquidity(bad_quote)
        self.assertFalse(valid)
        self.assertIn("Illiquid Trap", reason)

    def test_wide_spread_rejected(self):
        """Reject contracts with wide bid-ask spread (> $0.05 or > 5% mid)."""
        wide_quote = {"bid": 0.50, "ask": 0.65, "open_interest": 500, "volume": 100}
        valid, reason = validate_option_liquidity(wide_quote)
        self.assertFalse(valid)
        self.assertIn("exceeds cap", reason)

    def test_low_volume_oi_rejected(self):
        """Reject contracts with low open interest or volume."""
        low_activity_quote = {"bid": 0.50, "ask": 0.52, "open_interest": 10, "volume": 5}
        valid, reason = validate_option_liquidity(low_activity_quote)
        self.assertFalse(valid)
        self.assertIn("Low Liquidity", reason)

    def test_liquid_contract_accepted(self):
        """Accept high-liquidity, tight-spread contracts."""
        good_quote = {"bid": 0.50, "ask": 0.52, "open_interest": 1500, "volume": 300}
        valid, reason = validate_option_liquidity(good_quote)
        self.assertTrue(valid)
        self.assertEqual(reason, "Passed")

    # =========================================================================
    # TEST SET 2: FILL QUALITY SCORING (0.0 TO 10.0 SCALE)
    # =========================================================================

    def test_midpoint_fill_score(self):
        """Verify Midpoint fill receives a 5.0 / 10.0 score."""
        score = calculate_fill_quality_score(fill_price=0.73, bid=0.71, ask=0.75, side="buy")
        self.assertEqual(score, 5.0)

    def test_aapl_live_buy_fill_score(self):
        """Evaluate AAPL buy fill @ $0.74 (Bid: $0.71 / Ask: $0.76)."""
        score = calculate_fill_quality_score(fill_price=0.74, bid=0.71, ask=0.76, side="buy")
        self.assertEqual(score, 4.0)

    def test_nvda_live_buy_fill_score(self):
        """Evaluate NVDA buy fill @ $0.75 (Bid: $0.72 / Ask: $0.77)."""
        score = calculate_fill_quality_score(fill_price=0.75, bid=0.72, ask=0.77, side="buy")
        self.assertEqual(score, 4.0)

    # =========================================================================
    # TEST SET 3: STEPPED LIMIT EXIT EXECUTIONS (gex_exit_monitor.py)
    # =========================================================================

    @patch('src.gex_exit_monitor.get_live_bid_ask')
    @patch('requests.post')
    def test_stepped_close_limit_pricing(self, mock_post, mock_get_bid_ask):
        """Verify stepped exit uses midpoint limit order instead of raw market order."""
        mock_get_bid_ask.return_value = (0.40, 0.50, "https://sandbox.tradier.com/v1")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"order": {"id": 99999, "status": "ok"}}
        mock_post.return_value = mock_response

        success = execute_tradier_close_stepped("NVDA260828C00235000", "NVDA", 1)
        self.assertTrue(success)

        posted_payload = mock_post.call_args[1]['data']
        self.assertEqual(posted_payload['type'], 'limit')
        self.assertEqual(posted_payload['price'], '0.45')

    # =========================================================================
    # TEST SET 4: REALISTIC BID-BASED PNL EVALUATION (check_and_close_target.py)
    # =========================================================================

    @patch('src.gex_exit_monitor.get_live_bid_ask')
    @patch('boto3.resource')
    def test_pnl_calculated_against_bid_not_ask(self, mock_boto, mock_get_bid_ask):
        """Ensure PnL uses live Bid (liquidation value) instead of inflated Ask/Mark."""
        mock_get_bid_ask.return_value = (0.30, 0.80, "https://sandbox.tradier.com/v1")

        mock_dynamo = MagicMock()
        mock_table = MagicMock()
        mock_boto.return_value = mock_dynamo
        mock_dynamo.Table.return_value = mock_table
        
        mock_table.scan.return_value = {
            'Items': [{
                'ticker': 'NVDA',
                'occ_symbol': 'NVDA260828C00235000',
                'entry_price': '0.50',
                'shares': '1',
                'exit_status': 'ACTIVE'
            }]
        }

        ticker_brackets = {'NVDA': {'stop': None, 'target': 10.0}}

        with patch('src.gex_exit_monitor.execute_tradier_close_stepped') as mock_close:
            scan_and_close_targets(global_target=None, ticker_brackets=ticker_brackets)
            mock_close.assert_not_called()

if __name__ == '__main__':
    unittest.main()
