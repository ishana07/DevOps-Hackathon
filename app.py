import os
import sys
import csv
import io
import time
import socket
import ipaddress
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import Flask, request, jsonify, render_template, Response

# -----------------------------------------------------------------------------
# Application Configuration & Constants
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "pulsewatch.db")
DEFAULT_ENDPOINT = "https://httpbin.org/status/200"
DEFAULT_INTERVAL_SECONDS = 10
MIN_INTERVAL_SECONDS = 3
MAX_INTERVAL_SECONDS = 3600
REQUEST_TIMEOUT_SECONDS = 5.0

# SSRF Safeguard: Allow private IPs only if explicitly enabled via environment variable
ALLOW_PRIVATE_IPS = os.environ.get("PULSEWATCH_ALLOW_PRIVATE_IPS", "false").lower() in ("true", "1", "yes")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "pulsewatch-dev-secret-key-2026")
app.config["DB_PATH"] = DB_PATH

# Track application start time
APP_START_TIME = datetime.now(timezone.utc)

# Background worker synchronization
monitor_thread = None
monitor_stop_event = threading.Event()
monitor_wake_event = threading.Event()
config_lock = threading.Lock()


# -----------------------------------------------------------------------------
# Database Layer (SQLite with Parameterized Queries)
# -----------------------------------------------------------------------------
@contextmanager
def get_db_connection():
    """Context manager that yields a SQLite connection and guarantees closure."""
    path = app.config.get("DB_PATH", DB_PATH)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initializes the SQLite database tables and default configuration."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Configuration key-value table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        
        # Health check monitoring records table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                status_code INTEGER,
                response_time_ms REAL,
                status TEXT NOT NULL,
                error_message TEXT,
                check_type TEXT NOT NULL DEFAULT 'AUTOMATIC'
            )
        """)
        
        # Indexes for fast historical querying and stats aggregation
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_checks_timestamp ON checks(timestamp DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_checks_status ON checks(status)")

        # Seed default configuration if absent
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('endpoint', ?)", (DEFAULT_ENDPOINT,))
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('interval_seconds', ?)", (str(DEFAULT_INTERVAL_SECONDS),))
        cursor.execute("INSERT OR IGNORE INTO config (key, value) VALUES ('monitoring_enabled', 'true')")
        
        conn.commit()


def get_config_value(key, default=None):
    """Retrieves a configuration value by key."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM config WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else default


def set_config_value(key, value):
    """Sets or updates a configuration value."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO config (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, str(value)))
        conn.commit()


def get_all_config():
    """Retrieves all configuration settings."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM config")
        rows = cursor.fetchall()
        cfg = {row["key"]: row["value"] for row in rows}
        return {
            "endpoint": cfg.get("endpoint", DEFAULT_ENDPOINT),
            "interval_seconds": int(cfg.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)),
            "monitoring_enabled": cfg.get("monitoring_enabled", "true").lower() == "true",
            "allow_private_ips": ALLOW_PRIVATE_IPS
        }


# -----------------------------------------------------------------------------
# Security & URL Validation (SSRF Prevention)
# -----------------------------------------------------------------------------
def is_ip_private_or_reserved(ip_str):
    """Checks whether an IP address belongs to loopback, private, link-local, or reserved ranges."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        return True


def validate_url(url, allow_private=None):
    """
    Validates target URL scheme, syntax, and hostname destination.
    Protects against Server-Side Request Forgery (SSRF) targeting internal networks,
    localhost, link-local metadata endpoints (e.g. AWS 169.254.169.254), and private LANs.
    """
    if allow_private is None:
        allow_private = ALLOW_PRIVATE_IPS

    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string."

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        return False, f"Invalid scheme '{parsed.scheme}'. Only 'http' and 'https' are allowed."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must contain a valid domain name or host."

    # Validate port if explicitly specified
    try:
        if parsed.port:
            if not (1 <= parsed.port <= 65535):
                return False, "Port out of range (1-65535)."
    except ValueError:
        return False, "Port out of range (1-65535)."

    # Allow local mock endpoints on localhost / 127.0.0.1 for self-contained hackathon demo testing
    if hostname.lower() in ("127.0.0.1", "localhost") and parsed.path.startswith("/mock/"):
        return True, url

    # Resolve IP addresses for SSRF verification
    if not allow_private:
        try:
            # Resolve both IPv4 and IPv6 addresses
            addr_info = socket.getaddrinfo(hostname, None)
            resolved_ips = set(info[4][0] for info in addr_info)
            
            for ip in resolved_ips:
                if is_ip_private_or_reserved(ip):
                    return False, (
                        f"Target host '{hostname}' resolves to restricted/internal IP address ({ip}). "
                        "Access to localhost and private networks is blocked for security (SSRF prevention). "
                        "To permit internal testing, set PULSEWATCH_ALLOW_PRIVATE_IPS=1."
                    )
        except socket.gaierror:
            return False, f"Could not resolve host '{hostname}'. Please check DNS or domain spelling."
        except Exception as e:
            return False, f"Failed resolving target host: {str(e)}"

    return True, url


# -----------------------------------------------------------------------------
# Health Check Engine
# -----------------------------------------------------------------------------
def perform_health_check(endpoint, check_type="AUTOMATIC"):
    """
    Performs a real HTTP/HTTPS health check against the given endpoint.
    Records timestamp, latency in ms, status code, UP/DOWN result, and error details.
    Persists the check into SQLite.
    
    Definition:
    - UP: HTTP response with status code in the 2xx range (200-299).
    - DOWN: Any non-2xx status code (3xx, 4xx, 5xx), connection failure, timeout, or DNS error.
    """
    import requests

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    status_code = None
    response_time_ms = None
    status = "DOWN"
    error_message = None

    # Step 1: URL Validation & Security verification
    is_valid, validation_msg = validate_url(endpoint)
    if not is_valid:
        error_message = f"Validation Error: {validation_msg}"
        record = {
            "timestamp": timestamp,
            "endpoint": endpoint,
            "status_code": None,
            "response_time_ms": None,
            "status": "DOWN",
            "error_message": error_message,
            "check_type": check_type
        }
        _save_check_record(record)
        return record

    # Step 2: Execute HTTP GET with latency measurement
    headers = {
        "User-Agent": "PulseWatch-Monitor/1.0 (+https://github.com/DevOps/PulseWatch)"
    }
    
    start_time = time.perf_counter()
    try:
        response = requests.get(
            endpoint,
            timeout=REQUEST_TIMEOUT_SECONDS,
            headers=headers,
            allow_redirects=True
        )
        elapsed_seconds = time.perf_counter() - start_time
        response_time_ms = round(elapsed_seconds * 1000, 2)
        status_code = response.status_code

        # Healthy check defined as HTTP 2xx
        if 200 <= response.status_code < 300:
            status = "UP"
            error_message = None
        else:
            status = "DOWN"
            error_message = f"HTTP {response.status_code}: {response.reason}"

    except requests.exceptions.Timeout:
        elapsed_seconds = time.perf_counter() - start_time
        response_time_ms = round(elapsed_seconds * 1000, 2)
        status = "DOWN"
        error_message = f"Request timed out after {REQUEST_TIMEOUT_SECONDS}s"

    except requests.exceptions.SSLError as e:
        status = "DOWN"
        error_message = "SSL certificate verification failed"

    except requests.exceptions.ConnectionError as e:
        status = "DOWN"
        error_message = "Connection refused or host unreachable"

    except requests.exceptions.RequestException as e:
        status = "DOWN"
        error_message = f"Request error: {str(e)}"

    except Exception as e:
        status = "DOWN"
        error_message = f"Unexpected failure: {str(e)}"

    record = {
        "timestamp": timestamp,
        "endpoint": endpoint,
        "status_code": status_code,
        "response_time_ms": response_time_ms,
        "status": status,
        "error_message": error_message,
        "check_type": check_type
    }

    _save_check_record(record)
    return record


def _save_check_record(record):
    """Persists a single health check record using parameterized SQL."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO checks (timestamp, endpoint, status_code, response_time_ms, status, error_message, check_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            record["timestamp"],
            record["endpoint"],
            record["status_code"],
            record["response_time_ms"],
            record["status"],
            record["error_message"],
            record["check_type"]
        ))
        conn.commit()
        record["id"] = cursor.lastrowid


# -----------------------------------------------------------------------------
# Background Monitoring Loop
# -----------------------------------------------------------------------------
def background_monitoring_worker():
    """
    Background worker thread running periodic health checks.
    Supports dynamic interval updates and non-blocking shutdowns via threading.Event.
    """
    while not monitor_stop_event.is_set():
        try:
            config = get_all_config()
            endpoint = config.get("endpoint")
            interval = config.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)
            enabled = config.get("monitoring_enabled", True)

            if enabled and endpoint:
                perform_health_check(endpoint, check_type="AUTOMATIC")

            # Wait for the configured interval or wake up early on shutdown/config update
            monitor_wake_event.wait(timeout=interval)
            monitor_wake_event.clear()

        except Exception as e:
            # Prevent background worker crash
            time.sleep(2)


def start_background_monitoring():
    """Starts the background monitoring thread once, avoiding reloader duplicates."""
    global monitor_thread
    with config_lock:
        if monitor_thread is None or not monitor_thread.is_alive():
            monitor_stop_event.clear()
            monitor_wake_event.clear()
            monitor_thread = threading.Thread(target=background_monitoring_worker, daemon=True, name="PulseWatch-Worker")
            monitor_thread.start()


def stop_background_monitoring():
    """Stops the background monitoring thread cleanly."""
    global monitor_thread
    with config_lock:
        monitor_stop_event.set()
        monitor_wake_event.set()
        if monitor_thread and monitor_thread.is_alive():
            monitor_thread.join(timeout=1.0)
        monitor_thread = None


# -----------------------------------------------------------------------------
# SLA & Statistics Calculations
# -----------------------------------------------------------------------------
def calculate_sla_statistics():
    """
    Computes SLA and operational availability metrics across recorded checks:
    1. Availability % = (successful checks / total checks) * 100
    2. Average Response Time = mean of response_time_ms across recorded checks
    3. Estimated Downtime = failed_checks * interval_seconds (Interval-sampling estimate)
    4. Observed Outage Duration = sum of elapsed time during contiguous DOWN failure blocks
    5. Success and failure counts, min/max response times, and current service health.
    """
    config = get_all_config()
    interval_seconds = config.get("interval_seconds", DEFAULT_INTERVAL_SECONDS)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Total counts
        cursor.execute("SELECT COUNT(*) AS total FROM checks")
        total_checks = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS successful FROM checks WHERE status = 'UP'")
        successful_checks = cursor.fetchone()["successful"]

        failed_checks = total_checks - successful_checks

        # Response time statistics
        cursor.execute("""
            SELECT 
                AVG(response_time_ms) AS avg_time,
                MIN(response_time_ms) AS min_time,
                MAX(response_time_ms) AS max_time
            FROM checks
            WHERE response_time_ms IS NOT NULL
        """)
        time_stats = cursor.fetchone()
        avg_time = round(time_stats["avg_time"], 2) if time_stats["avg_time"] is not None else 0.0
        min_time = round(time_stats["min_time"], 2) if time_stats["min_time"] is not None else 0.0
        max_time = round(time_stats["max_time"], 2) if time_stats["max_time"] is not None else 0.0

        # Most recent check
        cursor.execute("SELECT * FROM checks ORDER BY id DESC LIMIT 1")
        last_check_row = cursor.fetchone()
        last_check = dict(last_check_row) if last_check_row else None

        # Reporting period and record range bounds
        cursor.execute("SELECT MIN(timestamp) AS start_time, MAX(timestamp) AS end_time FROM checks")
        bounds_row = cursor.fetchone()
        start_time = bounds_row["start_time"] if bounds_row else None
        end_time = bounds_row["end_time"] if bounds_row else None

    # Availability Percentage (Formula: successful_checks / total_checks * 100)
    # Safe against division by zero on empty dataset
    if total_checks > 0:
        availability_pct = round((successful_checks / total_checks) * 100, 2)
        start_fmt = start_time.replace("T", " ")[:19] + " UTC" if start_time else ""
        end_fmt = end_time.replace("T", " ")[:19] + " UTC" if end_time else ""
        if start_fmt == end_fmt:
            reporting_period = f"Probed at {start_fmt}"
        else:
            reporting_period = f"{start_fmt} to {end_fmt}"
        record_range = f"All {total_checks} Recorded Samples"
    else:
        availability_pct = 100.0  # Default clean SLA state
        reporting_period = "No records yet (Awaiting first probe)"
        record_range = "0 Samples Recorded"

    # Downtime Calculation 1: Interval-Sampled Estimated Downtime
    # Assumes each failed check sample represents an outage window of 1 interval
    estimated_downtime_seconds = failed_checks * interval_seconds

    # Downtime Calculation 2: Observed Outage Duration across contiguous failure periods
    observed_outage_seconds = _calculate_observed_outage_duration(interval_seconds)

    # Determine SLA Tier
    if availability_pct >= 99.9:
        sla_tier = "Three Nines (99.9%+)"
        sla_status = "EXCELLENT"
    elif availability_pct >= 99.0:
        sla_tier = "Two Nines (99.0%+)"
        sla_status = "HEALTHY"
    elif availability_pct >= 95.0:
        sla_tier = "Acceptable (95.0%+)"
        sla_status = "WARNING"
    else:
        sla_tier = "Critical SLA Breach (<95%)"
        sla_status = "CRITICAL"

    current_status = last_check["status"] if last_check else "UNKNOWN"

    return {
        "total_checks": total_checks,
        "successful_checks": successful_checks,
        "failed_checks": failed_checks,
        "availability_percentage": availability_pct,
        "sla_formula": "Availability (%) = (successful checks / total checks) * 100",
        "record_range": record_range,
        "reporting_period": reporting_period,
        "start_time_utc": start_time,
        "end_time_utc": end_time,
        "average_response_time_ms": avg_time,
        "min_response_time_ms": min_time,
        "max_response_time_ms": max_time,
        "estimated_downtime_seconds": estimated_downtime_seconds,
        "estimated_downtime_formatted": _format_duration(estimated_downtime_seconds),
        "observed_outage_seconds": observed_outage_seconds,
        "observed_outage_formatted": _format_duration(observed_outage_seconds),
        "downtime_explanation": (
            "Estimated Downtime represents the aggregate outage window calculated as "
            "(failed_checks * interval_seconds). It is an interval-sampled statistical estimate, "
            "whereas actual real-world outage duration between polling periods may vary slightly."
        ),
        "sla_tier": sla_tier,
        "sla_status": sla_status,
        "current_status": current_status,
        "last_check": last_check
    }


def _calculate_observed_outage_duration(interval_seconds):
    """
    Computes observed outage by scanning chronological check sequences.
    For each contiguous block of DOWN statuses, calculates elapsed duration
    from first DOWN to the next recovery UP (or last known DOWN + 1 interval).
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, status FROM checks ORDER BY id ASC")
        rows = cursor.fetchall()

    if not rows:
        return 0

    total_observed_seconds = 0
    in_outage = False
    outage_start_dt = None
    last_down_dt = None

    for r in rows:
        try:
            check_dt = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
        except ValueError:
            continue

        if r["status"] == "DOWN":
            if not in_outage:
                in_outage = True
                outage_start_dt = check_dt
            last_down_dt = check_dt
        else: # UP
            if in_outage:
                # Outage recovered at check_dt
                duration = (check_dt - outage_start_dt).total_seconds()
                total_observed_seconds += max(duration, interval_seconds)
                in_outage = False
                outage_start_dt = None
                last_down_dt = None

    # If currently still in outage at the end of the history
    if in_outage and outage_start_dt and last_down_dt:
        duration = (last_down_dt - outage_start_dt).total_seconds() + interval_seconds
        total_observed_seconds += max(duration, interval_seconds)

    return int(round(total_observed_seconds))


def _format_duration(seconds):
    """Formats seconds into human-readable duration strings (e.g. '2m 15s', '1h 4m')."""
    if seconds <= 0:
        return "0s"
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or not parts:
        parts.append(f"{secs}s")

    return " ".join(parts[:2])


# -----------------------------------------------------------------------------
# Web & API Routes
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    """Serves the single-page dashboard application."""
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def api_health():
    """PulseWatch internal service health endpoint."""
    uptime_seconds = int((datetime.now(timezone.utc) - APP_START_TIME).total_seconds())
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS total FROM checks")
        total_checks = cursor.fetchone()["total"]

    return jsonify({
        "status": "healthy",
        "service": "PulseWatch Service Availability & SLA Reporter",
        "version": "1.0.0",
        "uptime_seconds": uptime_seconds,
        "total_records_stored": total_checks,
        "server_time_utc": datetime.now(timezone.utc).isoformat()
    })


@app.route("/api/config", methods=["GET", "POST"])
def api_config():
    """Reads or updates endpoint monitoring configurations."""
    if request.method == "GET":
        return jsonify(get_all_config())

    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON body provided."}), 400

    # Validate and update endpoint if specified
    if "endpoint" in data:
        new_endpoint = str(data["endpoint"]).strip()
        is_valid, err_msg = validate_url(new_endpoint)
        if not is_valid:
            return jsonify({"error": f"Invalid URL: {err_msg}"}), 400
        set_config_value("endpoint", new_endpoint)

    # Validate and update interval
    if "interval_seconds" in data:
        try:
            new_interval = int(data["interval_seconds"])
            if not (MIN_INTERVAL_SECONDS <= new_interval <= MAX_INTERVAL_SECONDS):
                return jsonify({
                    "error": f"Interval must be between {MIN_INTERVAL_SECONDS} and {MAX_INTERVAL_SECONDS} seconds."
                }), 400
            set_config_value("interval_seconds", new_interval)
        except (ValueError, TypeError):
            return jsonify({"error": "Interval must be a valid integer."}), 400

    # Validate and update monitoring_enabled flag
    if "monitoring_enabled" in data:
        enabled = bool(data["monitoring_enabled"])
        set_config_value("monitoring_enabled", "true" if enabled else "false")

    # Signal the background worker to apply updated configuration immediately
    monitor_wake_event.set()

    return jsonify({
        "message": "Configuration successfully updated.",
        "config": get_all_config()
    })


@app.route("/api/check-now", methods=["POST"])
def api_check_now():
    """Manually triggers an immediate health check on the configured (or specified) endpoint."""
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint") if isinstance(data, dict) else None
    
    if not endpoint:
        config = get_all_config()
        endpoint = config.get("endpoint")

    if not endpoint:
        return jsonify({"error": "No endpoint configured for monitoring."}), 400

    result = perform_health_check(endpoint, check_type="MANUAL")
    stats = calculate_sla_statistics()
    return jsonify({
        "message": "Health check completed.",
        "check": result,
        "stats": stats
    })


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Returns SLA metrics, availability %, latency, and downtime calculations."""
    stats = calculate_sla_statistics()
    return jsonify(stats)


@app.route("/api/history", methods=["GET"])
def api_history():
    """Retrieves chronological health check records with limit and filtering."""
    try:
        limit = int(request.args.get("limit", 50))
        limit = max(1, min(limit, 500))  # Cap between 1 and 500
    except ValueError:
        limit = 50

    status_filter = request.args.get("status", "").upper()
    
    with get_db_connection() as conn:
        cursor = conn.cursor()
        if status_filter in ("UP", "DOWN"):
            cursor.execute("""
                SELECT * FROM checks 
                WHERE status = ? 
                ORDER BY id DESC LIMIT ?
            """, (status_filter, limit))
        else:
            cursor.execute("""
                SELECT * FROM checks 
                ORDER BY id DESC LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        history = [dict(r) for r in rows]

    return jsonify({
        "count": len(history),
        "history": history
    })


@app.route("/api/export.csv", methods=["GET"])
def api_export_csv():
    """Exports all recorded health checks as a timestamped CSV file."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, timestamp, endpoint, status, status_code, response_time_ms, error_message, check_type 
            FROM checks 
            ORDER BY id ASC
        """)
        rows = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write CSV Header
    writer.writerow([
        "ID",
        "Timestamp (UTC)",
        "Endpoint URL",
        "Health Status",
        "HTTP Status Code",
        "Response Time (ms)",
        "Error / Timeout Details",
        "Check Trigger"
    ])

    for row in rows:
        writer.writerow([
            row["id"],
            row["timestamp"],
            row["endpoint"],
            row["status"],
            row["status_code"] if row["status_code"] is not None else "",
            row["response_time_ms"] if row["response_time_ms"] is not None else "",
            row["error_message"] or "",
            row["check_type"]
        ])

    csv_data = output.getvalue()
    filename = f"pulsewatch_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Content-Type": "text/csv; charset=utf-8"
        }
    )


@app.route("/api/reset-data", methods=["POST"])
def api_reset_data():
    """Clears historical checks for demo reset purposes."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM checks")
        conn.commit()
    return jsonify({"message": "Health check history successfully cleared."})


# -----------------------------------------------------------------------------
# Built-In Mock Endpoints (For Offline / Hackathon Demonstrations)
# -----------------------------------------------------------------------------
@app.route("/mock/status/<int:code>")
def mock_status(code):
    """Returns requested HTTP status code for instant testing."""
    if code == 200:
        return jsonify({"mock": "success", "status": 200, "message": "Service operational."}), 200
    elif code == 204:
        return Response(status=204)
    elif code == 404:
        return jsonify({"mock": "error", "status": 404, "message": "Resource not found."}), 404
    elif code == 500:
        return jsonify({"mock": "error", "status": 500, "message": "Simulated Internal Server Error."}), 500
    elif code == 503:
        return jsonify({"mock": "error", "status": 503, "message": "Service Temporarily Unavailable."}), 503
    return jsonify({"mock": "response", "status": code}), code


@app.route("/mock/delay/<int:seconds>")
def mock_delay(seconds):
    """Simulates high latency or timeout response."""
    seconds = min(seconds, 10)
    time.sleep(seconds)
    return jsonify({"mock": "delayed", "delay_seconds": seconds, "status": 200})


# -----------------------------------------------------------------------------
# Application Startup Initialization
# -----------------------------------------------------------------------------
# Initialize database on module import
init_db()

# Start background monitoring thread (guarded against Flask reloader duplicate threads)
if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    start_background_monitoring()


if __name__ == "__main__":
    init_db()
    start_background_monitoring()
    port = int(os.environ.get("PORT", 5000))
    print(f"\n============================================================")
    print(f" PulseWatch Service Availability & SLA Reporter Starting")
    print(f" Web Dashboard: http://127.0.0.1:{port}")
    print(f" API Health:    http://127.0.0.1:{port}/api/health")
    print(f" SSRF Safety:   {'Private IPs Permitted' if ALLOW_PRIVATE_IPS else 'Active (Local/Private IPs Blocked)'}")
    print(f"============================================================\n")
    app.run(host="127.0.0.1", port=port, debug=False)
