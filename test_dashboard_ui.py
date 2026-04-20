import unittest

from app import app


class DashboardUiTests(unittest.TestCase):
    def test_dashboard_contains_structured_viewer_sections(self):
        client = app.test_client()
        response = client.get("/")
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Shopify import/export tool", html)
        self.assertIn('id="viewer-summary"', html)
        self.assertIn('id="viewer-table"', html)
        self.assertIn('id="viewer-empty"', html)
        self.assertIn('id="viewer-search"', html)
        self.assertIn('id="viewer-meta"', html)
        self.assertIn('id="viewer-column-picker"', html)
        self.assertIn('id="viewer-download-csv"', html)
        self.assertIn('id="viewer-preview"', html)
        self.assertIn('id="viewer-select-all-columns"', html)
        self.assertIn('id="viewer-clear-columns"', html)
        self.assertIn('id="viewer-pagination"', html)
        self.assertIn('id="viewer-page-size"', html)


if __name__ == "__main__":
    unittest.main()
