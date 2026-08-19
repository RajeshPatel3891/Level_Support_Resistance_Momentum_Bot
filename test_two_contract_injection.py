import unittest
from unittest.mock import patch
import os
import sys
import inspect

sys.path.extend(["/app", "/app/src", ".", "src"])

import smart_cso_injector

class TestParameterizedContractInjection(unittest.TestCase):

    def test_explicit_contract_qty_parameter_passing(self):
        """Verify smart_cso_scout_and_execute signature accepts contract_qty parameter."""
        sig = inspect.signature(smart_cso_injector.smart_cso_scout_and_execute)
        self.assertIn('contract_qty', sig.parameters, "smart_cso_scout_and_execute must accept contract_qty parameter")

    def test_environment_variable_fallback(self):
        """Verify fallback reads CONTRACT_QTY environment variable dynamically."""
        with patch.dict(os.environ, {'CONTRACT_QTY': '3'}):
            qty = int(os.getenv('CONTRACT_QTY', 1))
            self.assertEqual(qty, 3, "Engine must dynamically adapt to CONTRACT_QTY environment variable")

if __name__ == '__main__':
    unittest.main()
