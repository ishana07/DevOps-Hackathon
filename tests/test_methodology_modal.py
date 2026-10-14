import unittest
import os
import re
from app import app


class MethodologyModalTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_no_raw_latex_in_served_html(self):
        """Verify that raw LaTeX strings ($$, \\frac, \\text, \\times) are completely gone."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertNotIn("$$", html, "Raw LaTeX $$ delimiters should not appear in HTML")
        self.assertNotIn("\\frac", html, "Raw LaTeX \\frac commands should not appear in HTML")
        self.assertNotIn("\\text{", html, "Raw LaTeX \\text commands should not appear in HTML")
        self.assertNotIn("\\times", html, "Raw LaTeX \\times commands should not appear in HTML")

    def test_modal_structure_and_controls(self):
        """Verify methodology modal structure, headings, close buttons, and ack buttons."""
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        self.assertIn('id="methodology-modal"', html)
        self.assertIn('id="close-modal-btn"', html)
        self.assertIn('id="modal-ack-btn"', html)
        self.assertIn('Understood', html)
        self.assertIn('📐 SLA &amp; Downtime Calculation Methodology', html)

        # Verify all three section headings exist
        self.assertIn("1. Availability Percentage Formula", html)
        self.assertIn("2. Average Response Time", html)
        self.assertIn("3. Estimated Downtime vs. Continuous Outage", html)

    def test_all_formulas_rendered_as_html_math(self):
        """Verify each formula has its structured HTML math markup."""
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        # Formula 1: Availability
        self.assertIn("Availability (%)", html)
        self.assertIn("Successful Checks (HTTP 2xx)", html)
        self.assertIn("Total Checks", html)
        self.assertIn("formula-fraction", html)

        # Formula 2: Latency
        self.assertIn("Avg Latency (ms)", html)
        self.assertIn("formula-sigma", html)
        self.assertIn("&sum;", html)
        self.assertIn("Response Time<sub>i</sub>", html)

        # Formula 3: Estimated Downtime and Outage
        self.assertIn("Estimated Downtime", html)
        self.assertIn("Failed Checks Count", html)
        self.assertIn("Polling Interval (seconds)", html)
        self.assertIn("Observed Outage", html)

    def test_explanations_preserved(self):
        """Verify the crucial domain explanations are intact."""
        response = self.client.get("/")
        html = response.get_data(as_text=True)

        # HTTP 2xx success explanation
        self.assertIn("200–299", html)
        self.assertIn("DOWN", html)

        # Latency averaging explanation
        self.assertIn("Connection drops and unresolvable network failures are excluded from latency averaging", html)

        # Downtime sampling explanation for judges
        self.assertIn("Important Statistical Clarification for Judges:", html)
        self.assertIn("Interval-sampled monitoring polls at discrete intervals", html)

    def test_css_responsive_modal_rules(self):
        """Verify style.css contains responsive modal rules and formula classes."""
        css_path = os.path.join(os.path.dirname(__file__), "..", "static", "style.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()

        self.assertIn(".formula-box", css)
        self.assertIn(".formula-fraction", css)
        self.assertIn(".formula-sigma", css)
        self.assertIn(".sigma-symbol", css)
        self.assertIn("@media (max-width: 640px)", css)
        self.assertIn("overflow-x: auto", css)


if __name__ == "__main__":
    unittest.main()
