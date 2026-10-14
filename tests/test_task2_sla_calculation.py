import os
import sys
import tempfile

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app

def test_controlled_sla_calculation():
    print("=================================================================")
    print(" TASK 2: CONTROLLED AVAILABILITY SLA CALCULATION TEST")
    print("=================================================================")
    
    # 1. Use an isolated temporary SQLite database to protect production history
    db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    
    original_db = app.DB_PATH
    app.DB_PATH = temp_db_path
    app.app.config["DB_PATH"] = temp_db_path
    app.app.config["TESTING"] = True
    app.init_db()

    print(f"[+] Using isolated temporary database: {temp_db_path}")
    print(f"[+] Production database protected: {original_db}")

    try:
        # A. Empty Dataset Test (Division by Zero Protection)
        print("\n--- Test A: Empty Dataset (0 checks) ---")
        empty_stats = app.calculate_sla_statistics()
        print(f"Total Checks:            {empty_stats['total_checks']}")
        print(f"Successful Checks:       {empty_stats['successful_checks']}")
        print(f"Failed Checks:           {empty_stats['failed_checks']}")
        print(f"Availability Percentage: {empty_stats['availability_percentage']}%")
        print(f"Reporting Scope:         {empty_stats['record_range']}")
        print(f"Period:                  {empty_stats['reporting_period']}")
        assert empty_stats["total_checks"] == 0
        assert empty_stats["availability_percentage"] == 100.0
        print(">>> Test A PASSED: Empty dataset handled safely with 0 checks and 100.0% clean SLA.")

        # B. Task 2 Core Test: 9 Successful Checks + 1 Failed Check = 90.0% Availability
        print("\n--- Test B: Controlled 9 Successful Checks + 1 Failed Check ---")
        print("Inserting 9 successful checks (HTTP 200 UP)...")
        for i in range(1, 10):
            record = {
                "timestamp": f"2026-10-14T05:00:{i:02d}.000Z",
                "endpoint": "https://api.example.com/health",
                "status_code": 200,
                "response_time_ms": 45.0 + i,
                "status": "UP",
                "error_message": None,
                "check_type": "AUTOMATIC"
            }
            app._save_check_record(record)
            print(f"  [UP] Check #{i}: HTTP 200 (45.{i}ms)")

        print("\nInserting 1 failed check (HTTP 500 DOWN)...")
        fail_record = {
            "timestamp": "2026-10-14T05:00:10.000Z",
            "endpoint": "https://api.example.com/health",
            "status_code": 500,
            "response_time_ms": 135.5,
            "status": "DOWN",
            "error_message": "HTTP 500: Internal Server Error",
            "check_type": "AUTOMATIC"
        }
        app._save_check_record(fail_record)
        print("  [DOWN] Check #10: HTTP 500 (Internal Server Error)")

        # Query SLA calculation from SQLite records
        stats = app.calculate_sla_statistics()

        print("\n--- Calculated SLA Statistics Output ---")
        print(f"SLA Formula:             {stats['sla_formula']}")
        print(f"Total Checks:            {stats['total_checks']}")
        print(f"Successful Checks (UP):  {stats['successful_checks']}")
        print(f"Failed Checks (DOWN):    {stats['failed_checks']}")
        print(f"Availability Percentage: {stats['availability_percentage']}%")
        print(f"SLA Tier:                {stats['sla_tier']} ({stats['sla_status']})")
        print(f"Record Range Scope:      {stats['record_range']}")
        print(f"Reporting Period:        {stats['reporting_period']}")
        print(f"Average Response Time:   {stats['average_response_time_ms']} ms")
        print(f"Estimated Downtime:      {stats['estimated_downtime_formatted']}")

        # Assertions
        assert stats["total_checks"] == 10, f"Expected 10 total checks, got {stats['total_checks']}"
        assert stats["successful_checks"] == 9, f"Expected 9 successful checks, got {stats['successful_checks']}"
        assert stats["failed_checks"] == 1, f"Expected 1 failed check, got {stats['failed_checks']}"
        assert stats["availability_percentage"] == 90.0, f"Expected 90.0% availability, got {stats['availability_percentage']}%"
        assert stats["record_range"] == "All 10 Recorded Samples"

        print("\n>>> TEST B PASSED: (9 successful / 10 total) * 100 = 90.0% EXACTLY.")

        # C. Verify REST API Agreement
        print("\n--- Test C: Backend API /api/stats Agreement ---")
        client = app.app.test_client()
        api_resp = client.get("/api/stats")
        assert api_resp.status_code == 200
        api_data = api_resp.get_json()
        assert api_data["total_checks"] == 10
        assert api_data["successful_checks"] == 9
        assert api_data["failed_checks"] == 1
        assert api_data["availability_percentage"] == 90.0
        print(">>> Test C PASSED: REST API /api/stats matches database calculation 100%.")

        print("\n=================================================================")
        print(" ALL TASK 2 TESTS COMPLETED SUCCESSFULLY!")
        print("=================================================================")

    finally:
        # Restore production database path and cleanup temporary database
        app.DB_PATH = original_db
        app.app.config["DB_PATH"] = original_db
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
        print(f"[+] Cleaned up temporary test database. Production DB is untouched.")

if __name__ == "__main__":
    test_controlled_sla_calculation()
