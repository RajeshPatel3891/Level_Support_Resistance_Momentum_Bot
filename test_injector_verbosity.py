import unittest
from unittest.mock import patch, MagicMock
import io
import sys
import os

sys.path.extend([".", "src", "/app", "/app/src"])

import smart_cso_injector

class TestInjectorResponseVerbosity(unittest.TestCase):

    @patch('smart_cso_injector.requests.post')
    def test_tradier_http_200_error_payload_verbosity(self, mock_post):
        """Verify smart_cso_injector captures HTTP 200 error payloads and surfaces verbose reason."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "errors": {
                "error": "Margin requirement not met: Option Buying Power Exceeded"
            }
        }
        mock_post.return_value = mock_response

        captured_output = io.StringIO()
        sys.stdout = captured_output

        try:
            res = smart_cso_injector.smart_cso_scout_and_execute('SNAP')
        finally:
            sys.stdout = sys.__stdout__

        output_str = captured_output.getvalue()

        print("\n" + "="*60)
        print("🔍 CAPTURED INJECTOR LOG OUTPUT:")
        print("="*60)
        print(output_str if output_str.strip() else "[NO STDOUT CAPTURED]")
        print("="*60)

        # Ensure the verbose error string is printed to output
        self.assertIn("Margin requirement not met", output_str, "Output must contain the verbose rejection reason from Tradier")
        print("\n[✓] VERBOSITY ASSERTION PASSED: Rejection reason printed cleanly!")

if __name__ == '__main__':
    unittest.main()
