import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import requests

# Add parent directory to sys.path so app can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app


class PulseWatchTestCase(unittest.TestCase):
    def setUp(self):
        """Set up an isolated SQLite database for each test."""
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(self.db_fd)  # Close immediately to prevent Windows file lock
        app.DB_PATH = self.db_path
        app.app.config["TESTING"] = True
        app.app.config["DB_PATH"] = self.db_path
        app.init_db()
        self.client = app.app.test_client()

    def tearDown(self):
        """Clean up the temporary SQLite database file."""
        app.stop_background_monitoring()
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except OSError:
            pass

    # -------------------------------------------------------------------------
    # 1. Successful HTTP Responses (2xx)
    # -------------------------------------------------------------------------
    @patch("requests.get")
    def test_successful_http_response_200(self, mock_get):
        """Test health check handling of HTTP 200 OK."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.reason = "OK"
        mock_get.return_value = mock_resp

        # Use an endpoint that passes SSRF validation
        record = app.perform_health_check("https://httpbin.org/status/200", check_type="MANUAL")

        self.assertEqual(record["status"], "UP")
        self.assertEqual(record["status_code"], 200)
        self.assertIsNone(record["error_message"])
        self.assertIsNotNone(record["response_time_ms"])
        self.assertGreater(record["response_time_ms"], 0)

    @patch("requests.get")
    def test_successful_http_response_204(self, mock_get):
        """Test health check handling of HTTP 204 No Content (still 2xx UP)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_resp.reason = "No Content"
        mock_get.return_value = mock_resp

        record = app.perform_health_check("https://httpbin.org/status/204", check_type="AUTOMATIC")

        self.assertEqual(record["status"], "UP")
        self.assertEqual(record["status_code"], 204)
        self.assertIsNone(record["error_message"])

    # -------------------------------------------------------------------------
    # 2. Non-2xx HTTP Responses (4xx, 5xx)
    # -------------------------------------------------------------------------
    @patch("requests.get")
    def test_non_2xx_http_response_404(self, mock_get):
        """Test health check handling of HTTP 404 Not Found (DOWN)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.reason = "Not Found"
        mock_get.return_value = mock_resp

        record = app.perform_health_check("https://httpbin.org/status/404")

        self.assertEqual(record["status"], "DOWN")
        self.assertEqual(record["status_code"], 404)
        self.assertIn("404", record["error_message"])

    @patch("requests.get")
    def test_non_2xx_http_response_500(self, mock_get):
        """Test health check handling of HTTP 500 Internal Server Error (DOWN)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.reason = "Internal Server Error"
        mock_get.return_value = mock_resp

        record = app.perform_health_check("https://httpbin.org/status/500")

        self.assertEqual(record["status"], "DOWN")
        self.assertEqual(record["status_code"], 500)
        self.assertIn("500", record["error_message"])

    @patch("requests.get")
    def test_non_2xx_http_response_503(self, mock_get):
        """Test health check handling of HTTP 503 Service Unavailable (DOWN)."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.reason = "Service Unavailable"
        mock_get.return_value = mock_resp

        record = app.perform_health_check("https://httpbin.org/status/503")

        self.assertEqual(record["status"], "DOWN")
        self.assertEqual(record["status_code"], 503)
        self.assertIn("503", record["error_message"])
        self.assertIn("Service Unavailable", record["error_message"])

    # -------------------------------------------------------------------------
    # 3. Connection Errors
    # -------------------------------------------------------------------------
    @patch("requests.get")
    def test_connection_error_handling(self, mock_get):
        """Test handling when host is unreachable or connection is refused."""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        record = app.perform_health_check("https://httpbin.org/unreachable")

        self.assertEqual(record["status"], "DOWN")
        self.assertIsNone(record["status_code"])
        self.assertIn("Connection refused", record["error_message"])

    # -------------------------------------------------------------------------
    # 4. Request Timeouts
    # -------------------------------------------------------------------------
    @patch("requests.get")
    def test_request_timeout_handling(self, mock_get):
        """Test handling when endpoint times out."""
        mock_get.side_effect = requests.exceptions.Timeout("Read timed out")

        record = app.perform_health_check("https://httpbin.org/delay/10")

        self.assertEqual(record["status"], "DOWN")
        self.assertIsNone(record["status_code"])
        self.assertIn("timed out", record["error_message"].lower())

    # -------------------------------------------------------------------------
    # 5. Invalid URL Input & SSRF Protection
    # -------------------------------------------------------------------------
    def test_invalid_url_input(self):
        """Test URL validation rejecting invalid protocols, empty hosts, and bad formats."""
        # Non-HTTP scheme
        valid, msg = app.validate_url("ftp://ftp.example.com/file")
        self.assertFalse(valid)
        self.assertIn("Invalid scheme", msg)

        # Empty string
        valid, msg = app.validate_url("")
        self.assertFalse(valid)

        # Missing host
        valid, msg = app.validate_url("http://")
        self.assertFalse(valid)

        # Invalid port
        valid, msg = app.validate_url("https://example.com:99999/health")
        self.assertFalse(valid)
        self.assertIn("Port out of range", msg)

    def test_ssrf_prevention_on_private_ips(self):
        """Test SSRF protection blocking localhost and RFC 1918 private IPs."""
        # Localhost loopback
        valid, msg = app.validate_url("http://127.0.0.1:8080/metrics", allow_private=False)
        self.assertFalse(valid)
        self.assertIn("restricted/internal IP", msg)

        # AWS / Cloud Metadata endpoint
        valid, msg = app.validate_url("http://169.254.169.254/latest/meta-data/", allow_private=False)
        self.assertFalse(valid)
        self.assertIn("restricted/internal IP", msg)

        # Private RFC 1918 LAN
        valid, msg = app.validate_url("http://192.168.1.1/admin", allow_private=False)
        self.assertFalse(valid)
        self.assertIn("restricted/internal IP", msg)

    # -------------------------------------------------------------------------
    # 6. Availability Percentage Calculations
    # -------------------------------------------------------------------------
    def test_availability_calculation_empty_dataset(self):
        """Test availability calculation with 0 records returns 100.0% clean SLA state."""
        stats = app.calculate_sla_statistics()
        self.assertEqual(stats["total_checks"], 0)
        self.assertEqual(stats["successful_checks"], 0)
        self.assertEqual(stats["failed_checks"], 0)
        self.assertEqual(stats["availability_percentage"], 100.0)

    def test_availability_calculation_mixed_results(self):
        """Test exact calculation: 3 UP, 1 DOWN = 75.0% availability."""
        records = [
            {"timestamp": "2026-10-14T01:00:00.000Z", "endpoint": "https://test.com", "status_code": 200, "response_time_ms": 50.0, "status": "UP", "error_message": None, "check_type": "AUTOMATIC"},
            {"timestamp": "2026-10-14T01:00:10.000Z", "endpoint": "https://test.com", "status_code": 200, "response_time_ms": 60.0, "status": "UP", "error_message": None, "check_type": "AUTOMATIC"},
            {"timestamp": "2026-10-14T01:00:20.000Z", "endpoint": "https://test.com", "status_code": 500, "response_time_ms": 120.0, "status": "DOWN", "error_message": "HTTP 500", "check_type": "AUTOMATIC"},
            {"timestamp": "2026-10-14T01:00:30.000Z", "endpoint": "https://test.com", "status_code": 200, "response_time_ms": 40.0, "status": "UP", "error_message": None, "check_type": "AUTOMATIC"},
        ]
        for r in records:
            app._save_check_record(r)

        stats = app.calculate_sla_statistics()
        self.assertEqual(stats["total_checks"], 4)
        self.assertEqual(stats["successful_checks"], 3)
        self.assertEqual(stats["failed_checks"], 1)
        self.assertEqual(stats["availability_percentage"], 75.0)

    def test_availability_calculation_9_success_1_fail(self):
        """
        TASK 2 REQUIREMENT:
        Test the calculation using 9 successful checks and 1 failed check.
        Expected availability: 90.0%.
        Uses isolated temporary database so production history is not touched.
        """
        # Insert 9 UP checks (HTTP 200)
        for i in range(9):
            app._save_check_record({
                "timestamp": f"2026-10-14T01:00:{i:02d}.000Z",
                "endpoint": "https://api.example.com/health",
                "status_code": 200,
                "response_time_ms": 40.0 + i,
                "status": "UP",
                "error_message": None,
                "check_type": "AUTOMATIC"
            })

        # Insert 1 DOWN check (HTTP 500)
        app._save_check_record({
            "timestamp": "2026-10-14T01:00:10.000Z",
            "endpoint": "https://api.example.com/health",
            "status_code": 500,
            "response_time_ms": 120.0,
            "status": "DOWN",
            "error_message": "HTTP 500: Internal Server Error",
            "check_type": "AUTOMATIC"
        })

        stats = app.calculate_sla_statistics()
        self.assertEqual(stats["total_checks"], 10)
        self.assertEqual(stats["successful_checks"], 9)
        self.assertEqual(stats["failed_checks"], 1)
        self.assertEqual(stats["availability_percentage"], 90.0)
        self.assertEqual(stats["record_range"], "All 10 Recorded Samples")
        self.assertIn("UTC", stats["reporting_period"])
        self.assertEqual(stats["sla_formula"], "Availability (%) = (successful checks / total checks) * 100")

    # -------------------------------------------------------------------------
    # 7. Average Response Time Calculations
    # -------------------------------------------------------------------------
    def test_average_response_time_calculation(self):
        """Test average latency calculation: (50 + 100 + 150) / 3 = 100.0 ms."""
        records = [
            {"timestamp": "2026-10-14T01:00:00.000Z", "endpoint": "https://test.com", "status_code": 200, "response_time_ms": 50.0, "status": "UP", "error_message": None, "check_type": "AUTOMATIC"},
            {"timestamp": "2026-10-14T01:00:10.000Z", "endpoint": "https://test.com", "status_code": 200, "response_time_ms": 100.0, "status": "UP", "error_message": None, "check_type": "AUTOMATIC"},
            {"timestamp": "2026-10-14T01:00:20.000Z", "endpoint": "https://test.com", "status_code": 200, "response_time_ms": 150.0, "status": "UP", "error_message": None, "check_type": "AUTOMATIC"},
            {"timestamp": "2026-10-14T01:00:30.000Z", "endpoint": "https://test.com", "status_code": None, "response_time_ms": None, "status": "DOWN", "error_message": "DNS Error", "check_type": "AUTOMATIC"},
        ]
        for r in records:
            app._save_check_record(r)

        stats = app.calculate_sla_statistics()
        self.assertEqual(stats["average_response_time_ms"], 100.0)
        self.assertEqual(stats["min_response_time_ms"], 50.0)
        self.assertEqual(stats["max_response_time_ms"], 150.0)

    # -------------------------------------------------------------------------
    # 8. Downtime Estimation & Explanation
    # -------------------------------------------------------------------------
    def test_estimated_downtime_calculation(self):
        """Test interval-sampled downtime: 2 failed checks * 10s interval = 20s estimated downtime."""
        app.set_config_value("interval_seconds", "10")
        records = [
            {"timestamp": "2026-10-14T01:00:00.000Z", "endpoint": "https://test.com", "status_code": 500, "response_time_ms": 50.0, "status": "DOWN", "error_message": "Error", "check_type": "AUTOMATIC"},
            {"timestamp": "2026-10-14T01:00:10.000Z", "endpoint": "https://test.com", "status_code": 500, "response_time_ms": 50.0, "status": "DOWN", "error_message": "Error", "check_type": "AUTOMATIC"},
            {"timestamp": "2026-10-14T01:00:20.000Z", "endpoint": "https://test.com", "status_code": 200, "response_time_ms": 50.0, "status": "UP", "error_message": None, "check_type": "AUTOMATIC"},
        ]
        for r in records:
            app._save_check_record(r)

        stats = app.calculate_sla_statistics()
        self.assertEqual(stats["failed_checks"], 2)
        self.assertEqual(stats["estimated_downtime_seconds"], 20)
        self.assertIn("interval-sampled statistical estimate", stats["downtime_explanation"].lower())

    # -------------------------------------------------------------------------
    # 9. Database Persistence (Parameterized SQL)
    # -------------------------------------------------------------------------
    def test_database_persistence(self):
        """Verify check records are correctly stored in and fetched from SQLite."""
        record = {
            "timestamp": "2026-10-14T10:30:00.000Z",
            "endpoint": "https://api.example.com/v1/health",
            "status_code": 200,
            "response_time_ms": 32.45,
            "status": "UP",
            "error_message": None,
            "check_type": "MANUAL"
        }
        app._save_check_record(record)
        self.assertIn("id", record)
        self.assertGreater(record["id"], 0)

        with app.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM checks WHERE id = ?", (record["id"],))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["endpoint"], "https://api.example.com/v1/health")
            self.assertEqual(row["status"], "UP")
            self.assertEqual(row["check_type"], "MANUAL")

    # -------------------------------------------------------------------------
    # 10. CSV Export
    # -------------------------------------------------------------------------
    def test_csv_export(self):
        """Test GET /api/export.csv returns a valid CSV file with expected headers."""
        record = {
            "timestamp": "2026-10-14T12:00:00.000Z",
            "endpoint": "https://httpbin.org/status/200",
            "status_code": 200,
            "response_time_ms": 45.1,
            "status": "UP",
            "error_message": None,
            "check_type": "AUTOMATIC"
        }
        app._save_check_record(record)

        response = self.client.get("/api/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["Content-Type"])
        self.assertIn("pulsewatch_history_", response.headers["Content-Disposition"])

        csv_text = response.data.decode("utf-8")
        lines = csv_text.strip().split("\r\n") if "\r\n" in csv_text else csv_text.strip().split("\n")
        
        # Verify Header Line
        self.assertIn("Timestamp (UTC)", lines[0])
        self.assertIn("Endpoint URL", lines[0])
        self.assertIn("Health Status", lines[0])
        
        # Verify Record Line
        self.assertIn("https://httpbin.org/status/200", lines[1])
        self.assertIn("UP", lines[1])

    def test_sla_summary_csv_export(self):
        """Test GET /api/export-sla.csv returns executive summary SLA CSV."""
        record = {
            "timestamp": "2026-10-14T12:00:00.000Z",
            "endpoint": "https://httpbin.org/status/200",
            "status_code": 200,
            "response_time_ms": 45.1,
            "status": "UP",
            "error_message": None,
            "check_type": "AUTOMATIC"
        }
        app._save_check_record(record)

        # Test both direct route and ?type=summary
        resp_direct = self.client.get("/api/export-sla.csv")
        resp_param = self.client.get("/api/export.csv?type=summary")

        for response in (resp_direct, resp_param):
            self.assertEqual(response.status_code, 200)
            self.assertIn("text/csv", response.headers["Content-Type"])
            self.assertIn("pulsewatch_sla_summary_", response.headers["Content-Disposition"])

            csv_text = response.data.decode("utf-8")
            self.assertIn("PulseWatch - Service Availability & SLA Summary Report", csv_text)
            self.assertIn("Availability (%)", csv_text)
            self.assertIn("Total Health Checks", csv_text)
            self.assertIn("Estimated Downtime", csv_text)
            self.assertIn("Reporting Scope", csv_text)

    # -------------------------------------------------------------------------
    # 11. API Error Responses & Input Validation
    # -------------------------------------------------------------------------
    def test_api_config_invalid_payloads(self):
        """Test POST /api/config returns 400 Bad Request on invalid payloads."""
        # Non-JSON / empty body
        resp = self.client.post("/api/config", data="not json", content_type="application/json")
        self.assertEqual(resp.status_code, 400)

        # Invalid URL scheme
        resp = self.client.post("/api/config", json={"endpoint": "invalid://not-http"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.get_json())

        # SSRF forbidden target
        resp = self.client.post("/api/config", json={"endpoint": "http://127.0.0.1:9000"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("restricted/internal IP", resp.get_json()["error"])

        # Interval below minimum
        resp = self.client.post("/api/config", json={"interval_seconds": 1})
        self.assertEqual(resp.status_code, 400)

        # Interval above maximum
        resp = self.client.post("/api/config", json={"interval_seconds": 50000})
        self.assertEqual(resp.status_code, 400)

    # -------------------------------------------------------------------------
    # 12. App Health Check Endpoint
    # -------------------------------------------------------------------------
    def test_api_health_endpoint(self):
        """Test GET /api/health returns application metadata and uptime."""
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["service"], "PulseWatch Service Availability & SLA Reporter")
        self.assertIn("uptime_seconds", data)


if __name__ == "__main__":
    unittest.main()
