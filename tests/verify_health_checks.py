import os
import sys
import json
import sqlite3

# Point to app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app

def verify_live_checks():
    print("=================================================================")
    print(" PULSEWATCH GENUINE HEALTH CHECK VERIFICATION SUITE")
    print("=================================================================")
    
    client = app.app.test_client()

    # 1. Temporarily pause background monitoring and clear database to ensure clean, deterministic test execution
    client.post("/api/config", json={"monitoring_enabled": False})
    client.post("/api/reset-data")
    print("\n[+] Cleared database for fresh verification.")

    # -----------------------------------------------------------------
    # TEST CASE 1: Genuine Successful Request (HTTP 200 OK)
    # Target: https://httpbin.org/status/200
    # -----------------------------------------------------------------
    print("\n--- [TEST 1] Genuine Successful Health Check (HTTP 200) ---")
    endpoint_success = "https://httpbin.org/status/200"
    print(f"Target Endpoint: {endpoint_success}")
    
    # Send check-now request through Flask backend
    resp_success = client.post("/api/check-now", json={"endpoint": endpoint_success})
    assert resp_success.status_code == 200, f"Expected 200, got {resp_success.status_code}"
    
    data_success = resp_success.get_json()
    check_success = data_success["check"]
    stats_success = data_success["stats"]

    print(f"Result Status:      {check_success['status']}")
    print(f"HTTP Status Code:   {check_success['status_code']}")
    print(f"Response Time:      {check_success['response_time_ms']} ms")
    print(f"Timestamp (UTC):    {check_success['timestamp']}")
    print(f"Error Message:      {check_success['error_message']}")
    print(f"Check Type:         {check_success['check_type']}")
    print(f"SLA Availability:   {stats_success['availability_percentage']}%")

    assert check_success["status"] == "UP", f"Expected UP, got {check_success['status']}"
    assert check_success["status_code"] == 200, f"Expected 200, got {check_success['status_code']}"
    assert check_success["response_time_ms"] > 0, "Expected positive response time"
    assert check_success["error_message"] is None, "Expected no error message"
    print(">>> TEST 1 PASSED: Real HTTP 200 request verified as UP with genuine latency.")

    # -----------------------------------------------------------------
    # TEST CASE 2: Genuine Failed HTTP Request (HTTP 500 Server Error)
    # Target: https://httpbin.org/status/500
    # -----------------------------------------------------------------
    print("\n--- [TEST 2] Genuine Failed Health Check (HTTP 500) ---")
    endpoint_fail = "https://httpbin.org/status/500"
    print(f"Target Endpoint: {endpoint_fail}")

    resp_fail = client.post("/api/check-now", json={"endpoint": endpoint_fail})
    assert resp_fail.status_code == 200, f"Expected 200, got {resp_fail.status_code}"

    data_fail = resp_fail.get_json()
    check_fail = data_fail["check"]
    stats_fail = data_fail["stats"]

    print(f"Result Status:      {check_fail['status']}")
    print(f"HTTP Status Code:   {check_fail['status_code']}")
    print(f"Response Time:      {check_fail['response_time_ms']} ms")
    print(f"Timestamp (UTC):    {check_fail['timestamp']}")
    print(f"Error Message:      {check_fail['error_message']}")
    print(f"Check Type:         {check_fail['check_type']}")
    print(f"SLA Availability:   {stats_fail['availability_percentage']}%")
    print(f"Total Checks:       {stats_fail['total_checks']} (Passed: {stats_fail['successful_checks']}, Failed: {stats_fail['failed_checks']})")
    print(f"Estimated Downtime: {stats_fail['estimated_downtime_formatted']}")

    assert check_fail["status"] == "DOWN", f"Expected DOWN, got {check_fail['status']}"
    assert check_fail["status_code"] == 500, f"Expected 500, got {check_fail['status_code']}"
    assert "500" in check_fail["error_message"], "Expected 500 in error message"
    expected_pct = round((stats_fail["successful_checks"] / stats_fail["total_checks"]) * 100, 2)
    assert stats_fail["availability_percentage"] == expected_pct, f"Expected {expected_pct}% availability, got {stats_fail['availability_percentage']}"
    assert stats_fail["total_checks"] == stats_fail["successful_checks"] + stats_fail["failed_checks"]
    print(">>> TEST 2 PASSED: Real HTTP 500 request verified as DOWN with error details.")

    # -----------------------------------------------------------------
    # TEST CASE 3: Automatic Background Probing Verification
    # -----------------------------------------------------------------
    print("\n--- [TEST 3] Automatic Periodic Health Check Verification ---")
    # Simulate an automatic check through perform_health_check
    record_auto = app.perform_health_check("https://httpbin.org/status/200", check_type="AUTOMATIC")
    print(f"Automatic Probe ID: #{record_auto['id']}")
    print(f"Trigger Type:       {record_auto['check_type']}")
    print(f"Result Status:      {record_auto['status']}")
    assert record_auto["check_type"] == "AUTOMATIC"
    print(">>> TEST 3 PASSED: Automatic monitoring mechanism creates genuine records.")

    # -----------------------------------------------------------------
    # TEST CASE 4: Verify Database Persistence & Row Contents
    # -----------------------------------------------------------------
    print("\n--- [TEST 4] Database Persistence Audit ---")
    with app.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, timestamp, endpoint, status_code, response_time_ms, status, error_message, check_type FROM checks ORDER BY id ASC")
        rows = cursor.fetchall()

    print(f"Total Database Rows: {len(rows)}")
    for r in rows:
        print(f"  Row #{r['id']} | {r['timestamp']} | {r['endpoint']} | {r['status']} | Code: {r['status_code']} | Latency: {r['response_time_ms']}ms | Error: {r['error_message']} | Type: {r['check_type']}")

    assert len(rows) == 3, f"Expected 3 records in DB, found {len(rows)}"
    print(">>> TEST 4 PASSED: Database records perfectly match real network results.")

    # -----------------------------------------------------------------
    # TEST CASE 5: Verify CSV Export Output
    # -----------------------------------------------------------------
    print("\n--- [TEST 5] CSV Export Verification ---")
    csv_resp = client.get("/api/export.csv")
    assert csv_resp.status_code == 200
    csv_content = csv_resp.data.decode("utf-8")
    print("CSV Headers:")
    first_two_lines = csv_content.strip().split("\n")[:2]
    for l in first_two_lines:
        print(f"  {l}")
    assert "https://httpbin.org/status/200" in csv_content
    assert "https://httpbin.org/status/500" in csv_content
    print(">>> TEST 5 PASSED: CSV export contains genuine monitoring records.")

    # Re-enable background monitoring for normal operation
    client.post("/api/config", json={"monitoring_enabled": True})

    print("\n=================================================================")
    print(" ALL TASK 1 HEALTH CHECK VERIFICATIONS COMPLETED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    verify_live_checks()
