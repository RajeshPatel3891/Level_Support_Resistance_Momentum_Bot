import unittest
import os

class TestUITemplateGuards(unittest.TestCase):
    def test_js_card_value_selector_neutered(self):
        """[TEST] Asserts JavaScript DOM querySelector does not hijack .card-value or top metric cards."""
        with open("templates/index.html", "r", encoding="utf-8") as f:
            index_html = f.read()

        matrix_html = ""
        if os.path.exists("templates/matrix_rows.html"):
            with open("templates/matrix_rows.html", "r", encoding="utf-8") as f:
                matrix_html = f.read()

        combined_html = index_html + "\n" + matrix_html

        print("\n--------------------------------------------------")
        print("🔍 RUNNING DETAILED UI TEMPLATE GUARD VERIFICATION")
        print("--------------------------------------------------")

        # 1. Assert .card-value is NOT in querySelector
        self.assertNotIn(
            'document.querySelector(".card-value', 
            index_html, 
            "❌ REGRESSION: JS querySelector is still targeting .card-value!"
        )
        print("✓ [PASS] JS DOM querySelector is neutered (not targeting .card-value)")

        # 2. Assert Strategy Guards Header exists
        self.assertIn(
            "STRATEGY CONFIGURATION & GUARDS", 
            combined_html, 
            "❌ REGRESSION: Strategy Configuration & Guards card header missing!"
        )
        print("✓ [PASS] Strategy Configuration & Guards panel header verified")

        # 3. Assert $113,210.62 Sandbox baseline exists in shell or sub-templates
        self.assertIn(
            "113,210.62", 
            combined_html, 
            "❌ REGRESSION: $113,210.62 Sandbox baseline missing from templates!"
        )
        print("✓ [PASS] $113,210.62 Sandbox baseline string present in templates")
        print("--------------------------------------------------")

if __name__ == "__main__":
    unittest.main()
