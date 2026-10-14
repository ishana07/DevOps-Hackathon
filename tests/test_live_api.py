import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import app

def test_api_end_to_end():
    print(">>> Starting End-to-End API verification...")
    client = app.app.test_client()

    # 1. Test GET / (HTML Dashboard)
    resp = client.get("/")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    assert b"PulseWatch" in resp.data
    assert b"Service Availability &amp; SLA Monitor" in resp.data
    print("  [x] GET / loads successfully with complete HTML template")

    # 2. Test GET /api/health
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "healthy"
    print(f"  [x] GET /api/health returns healthy (Uptime: {data['uptime_seconds']}s)")

    # 3. Test GET /api/config
    resp = client.get("/api/config")
    assert resp.status_code == 200
    cfg = resp.get_json()
    assert "endpoint" in cfg
    assert "interval_seconds" in cfg
    print(f"  [x] GET /api/config returns active config: {cfg['endpoint']} (Interval: {cfg['interval_seconds']}s)")

    # 4. Test POST /mock/status/200 and /mock/status/500
    resp_200 = client.get("/mock/status/200")
    assert resp_200.status_code == 200
    resp_500 = client.get("/mock/status/500")
    assert resp_500.status_code == 500
    print("  [x] Mock endpoints /mock/status/200 and /mock/status/500 operational")

    # 5. Test POST /api/check-now
    resp = client.post("/api/check-now")
    assert resp.status_code == 200
    check_result = resp.get_json()
    assert "check" in check_result
    assert "stats" in check_result
    print(f"  [x] POST /api/check-now executed: Status={check_result['check']['status']}, HTTP={check_result['check']['status_code']}")

    # 6. Test GET /api/stats
    resp = client.get("/api/stats")
    assert resp.status_code == 200
    stats = resp.get_json()
    assert "availability_percentage" in stats
    assert "estimated_downtime_seconds" in stats
    print(f"  [x] GET /api/stats returns SLA: {stats['availability_percentage']}% (Total: {stats['total_checks']})")

    # 7. Test GET /api/history
    resp = client.get("/api/history?limit=10")
    assert resp.status_code == 200
    history = resp.get_json()
    assert "history" in history
    assert len(history["history"]) >= 1
    print(f"  [x] GET /api/history returned {len(history['history'])} records")

    # 8. Test GET /api/export.csv
    resp = client.get("/api/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["Content-Type"]
    csv_text = resp.data.decode("utf-8")
    assert "Timestamp (UTC)" in csv_text
    print(f"  [x] GET /api/export.csv generated valid CSV ({len(csv_text)} bytes)")

    print("\n>>> ALL END-TO-END API CHECKS PASSED PERFECTLY! <<<")

if __name__ == "__main__":
    test_api_end_to_end()
