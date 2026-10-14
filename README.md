# PulseWatch — Service Availability and SLA Reporter

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.x-green.svg)](https://flask.palletsprojects.com/)
[![Database](https://img.shields.io/badge/Database-SQLite3-lightgrey.svg)](https://www.sqlite.org/)
[![Frontend](https://img.shields.io/badge/Frontend-HTML5%20%7C%20CSS3%20%7C%20Vanilla%20JS-orange.svg)](#)
[![Charts](https://img.shields.io/badge/Charts-Chart.js-purple.svg)](https://www.chartjs.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](#)

> **BIT DevOps Community Hackathon 2026**  
> **Problem Statement 20:** Service Availability and SLA Reporter  
> **Difficulty Level:** Beginner – Intermediate  
> **Team Size:** 2 Members  

---

## 📌 Executive Summary

**PulseWatch** is a production-grade, lightweight Service Availability and SLA Reporting system designed for site reliability engineers (SREs) and DevOps teams. It continuously monitors HTTP/HTTPS microservices and web applications, measures sub-second response latency, detects outages, computes availability SLAs, and provides auditable historical reports with one-click CSV exports.

Built with a zero-bloat philosophy, PulseWatch relies exclusively on standard Python primitives, Flask, SQLite with parameterized SQL, Chart.js, and pure vanilla JavaScript—requiring no heavy dependencies, external paid APIs, or cloud vendor lock-in.

---

## 🏗️ System Architecture

```mermaid
flowchart TD
    subgraph Browser["User Browser (Single Page Dashboard)"]
        UI["Modern Dark Navy UI / Dashboard"]
        C1["Chart.js Latency Timeline"]
        C2["Chart.js Health Doughnut"]
        Table["Audit History Table & Filter"]
    end

    subgraph Backend["PulseWatch Flask Server (Python 3)"]
        Router["Flask API Gateway & Web Server"]
        Worker["Background Monitoring Worker Thread"]
        SSRF["SSRF Security Boundary & URL Validator"]
        Engine["Health Check Probe Engine (Requests)"]
        SLA["SLA & Downtime Analytics Engine"]
        CSVGen["Timestamped CSV Export Engine"]
    end

    subgraph Storage["Persistent Storage"]
        DB[("SQLite Database<br/>(pulsewatch.db)")]
    end

    subgraph Target["External / Internal Monitored Services"]
        ProdService["Production Web Service (HTTP/S)"]
        MockAPI["Built-in Hackathon Demo Mock (/mock/...)"]
    end

    UI -->|REST API Calls & Polling| Router
    Router -->|Trigger Check Now| Engine
    Router -->|Read / Write Config| DB
    Router -->|Read Stats & History| SLA
    Router -->|Download Report| CSVGen
    
    Worker -->|Read Config| DB
    Worker -->|Periodic Health Probes| SSRF
    SSRF -->|Validated HTTP/S Request| Engine
    Engine -->|HTTP Probes| ProdService
    Engine -->|Local Hackathon Demos| MockAPI
    Engine -->|Insert Records (Parameterized SQL)| DB
    SLA -->|Aggregate Queries| DB
    CSVGen -->|Fetch All Records| DB
    SLA --> Router
    Router -->|JSON Responses| Browser
```

---

## ⚡ Core Features

- **Configurable HTTP/HTTPS Endpoints**: Monitor any public service or API URL.
- **Dynamic Check Frequencies**: Polling intervals from 3s, 5s, 10s, 30s to 60s.
- **Instant "Check Now" Probes**: Manual zero-latency health check button with visual spinner.
- **Strict SLA Definition**: Health status strictly defined as HTTP `2xx` (`200–299`). Any `3xx`, `4xx`, `5xx`, timeout, or connection drop is categorized as **DOWN**.
- **Accurate Availability Metrics**: Mathematically sound SLA percentage calculation rounded to two decimals.
- **Latency Tracking**: Sub-millisecond response time measurement (`avg`, `min`, `max`).
- **Clear Downtime Methodology**: Interval-sampled downtime estimates clearly distinguished from continuous outage durations.
- **SSRF Security Protection**: Built-in protection against Server-Side Request Forgery targeting `localhost`, `127.0.0.1`, RFC 1918 private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), and cloud metadata services (`169.254.169.254`).
- **Interactive Visualizations**: Real-time Chart.js line charts for latency fluctuation and doughnut charts for uptime distribution.
- **Auditable Historical Log**: Searchable and filterable table of health checks (All, UP, DOWN).
- **One-Click CSV Export**: Download timestamped audit trails formatted for compliance reporting.
- **Built-in Mock Endpoints**: Offline testing routes (`/mock/status/200`, `/mock/status/500`, `/mock/status/404`, `/mock/delay/4`) for guaranteed offline hackathon demonstrations.

---

## 🧮 Mathematical Calculations & SLA Methodology

### 1. Availability Percentage
$$\text{Availability } (\%) = \left( \frac{\text{Successful Checks (HTTP 2xx)}}{\text{Total Checks}} \right) \times 100$$
- If `total_checks == 0`, availability defaults to `100.0%` (clean SLA initial state).
- Every probe is recorded with an immutable boolean determination: **UP** (2xx) or **DOWN** (non-2xx, timeout, or network failure).

### 2. Average Response Time
$$\text{Avg Latency (ms)} = \frac{1}{N} \sum_{i=1}^{N} \text{Response Time}_i \quad \text{(for checks where response was received)}$$
- Timed-out requests or unresolvable DNS connection failures without a completed TCP handshake do not produce a valid HTTP response time and are excluded from the latency mean to prevent statistical skew.

### 3. Estimated Downtime vs. Continuous Outage Duration
PulseWatch reports both interval-sampled estimated downtime and contiguous observed outage durations:

$$\text{Interval-Sampled Estimated Downtime} = \text{Failed Checks Count} \times \text{Polling Interval (seconds)}$$

> **⚠️ Clarification on Estimated vs. Actual Downtime:**  
> Interval-based health monitoring samples service status at discrete intervals (e.g. once every 10 seconds). If a service fails for 3 consecutive samples at a 10-second interval, the estimated downtime is **30 seconds**.  
> This is an **interval-based statistical estimate**. In the physical world, an outage might have started 2 seconds before the first failed probe or recovered 1 second before the next successful probe. Without continuous streaming or push-based APM agents running on the host, discrete polling provides an upper/lower sample-window estimate.

---

## 🚀 Quick Start & Installation (Windows)

### Prerequisites
- Python 3.10 or higher installed (`python --version`)
- Git installed (`git --version`)

### Step 1: Open Terminal in Project Directory
Open PowerShell or Command Prompt:
```powershell
cd c:\Users\JITHESH\Desktop\DevOps\PulseWatch
```

### Step 2: Create and Activate Virtual Environment
```powershell
# Create virtual environment
python -m venv venv

# Activate virtual environment (PowerShell)
.\venv\Scripts\Activate.ps1

# (If PowerShell displays an ExecutionPolicy error, run: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass)
```

### Step 3: Install Required Packages
```powershell
pip install -r requirements.txt
```

### Step 4: Run the Application
```powershell
python app.py
```
Output:
```text
============================================================
 PulseWatch Service Availability & SLA Reporter Starting
 Web Dashboard: http://127.0.0.1:5000
 API Health:    http://127.0.0.1:5000/api/health
 SSRF Safety:   Active (Local/Private IPs Blocked)
============================================================
```

### Step 5: Access the Dashboard
Open your web browser and navigate to:
👉 **`http://127.0.0.1:5000`**

---

## 🧪 Running Automated Tests

PulseWatch includes a comprehensive test suite (`tests/test_pulsewatch.py`) using Python's `unittest` framework and `unittest.mock` to verify all components without external internet dependencies.

Run the test suite:
```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

### Test Coverage Summary:
| Test Case | Description | Result |
| :--- | :--- | :---: |
| `test_successful_http_response_200` | Mocked 200 OK response verification | `PASSED` |
| `test_successful_http_response_204` | Mocked 204 No Content verification | `PASSED` |
| `test_non_2xx_http_response_404` | Mocked 404 Not Found error handling | `PASSED` |
| `test_non_2xx_http_response_500` | Mocked 500 Server Error error handling | `PASSED` |
| `test_connection_error_handling` | Network failure / connection refused handling | `PASSED` |
| `test_request_timeout_handling` | Request timeout exception handling | `PASSED` |
| `test_invalid_url_input` | Malformed URLs, bad schemes, invalid ports | `PASSED` |
| `test_ssrf_prevention_on_private_ips` | Blocking loopback, link-local, private subnets | `PASSED` |
| `test_availability_calculation_empty` | Empty dataset 100.0% clean SLA edge case | `PASSED` |
| `test_availability_calculation_mixed` | Exact arithmetic check (3 UP, 1 DOWN = 75%) | `PASSED` |
| `test_average_response_time_calculation` | Mean response time calculation across samples | `PASSED` |
| `test_estimated_downtime_calculation` | Interval-based downtime estimation formula | `PASSED` |
| `test_database_persistence` | Parameterized SQLite write & read verification | `PASSED` |
| `test_csv_export` | CSV generation, MIME headers, and column validation | `PASSED` |
| `test_api_config_invalid_payloads` | 400 Bad Request error response validation | `PASSED` |
| `test_api_health_endpoint` | App self-health status and uptime checks | `PASSED` |

---

## 🌐 API Reference

### 1. Application Health
- **Endpoint:** `GET /api/health`
- **Description:** Verifies PulseWatch server health, uptime, and database records.
- **Response:**
  ```json
  {
    "service": "PulseWatch Service Availability & SLA Reporter",
    "status": "healthy",
    "total_records_stored": 42,
    "uptime_seconds": 120,
    "version": "1.0.0"
  }
  ```

### 2. Read / Update Configuration
- **Endpoint:** `GET /api/config`
- **Endpoint:** `POST /api/config`
- **Request Body (JSON):**
  ```json
  {
    "endpoint": "https://httpbin.org/status/200",
    "interval_seconds": 10,
    "monitoring_enabled": true
  }
  ```

### 3. Immediate Health Check ("Check Now")
- **Endpoint:** `POST /api/check-now`
- **Description:** Instantly executes a synchronous probe on the active endpoint.
- **Response:**
  ```json
  {
    "message": "Health check completed.",
    "check": {
      "check_type": "MANUAL",
      "endpoint": "https://httpbin.org/status/200",
      "error_message": null,
      "id": 1,
      "response_time_ms": 112.45,
      "status": "UP",
      "status_code": 200,
      "timestamp": "2026-10-14T04:20:00.123Z"
    },
    "stats": { ... }
  }
  ```

### 4. SLA & Operational Statistics
- **Endpoint:** `GET /api/stats`
- **Response:**
  ```json
  {
    "availability_percentage": 97.5,
    "average_response_time_ms": 118.4,
    "current_status": "UP",
    "downtime_explanation": "Estimated Downtime represents the aggregate outage window calculated as (failed_checks * interval_seconds)...",
    "estimated_downtime_formatted": "20s",
    "estimated_downtime_seconds": 20,
    "failed_checks": 2,
    "max_response_time_ms": 240.5,
    "min_response_time_ms": 45.2,
    "observed_outage_formatted": "18s",
    "observed_outage_seconds": 18,
    "sla_status": "HEALTHY",
    "sla_tier": "Two Nines (99.0%+)",
    "successful_checks": 78,
    "total_checks": 80
  }
  ```

### 5. Historical Check Log
- **Endpoint:** `GET /api/history?limit=50&status=DOWN`
- **Query Params:** `limit` (int, default 50), `status` (`UP`, `DOWN`, or empty for all).

### 6. Export CSV
- **Endpoint:** `GET /api/export.csv`
- **Description:** Streams a download attachment `pulsewatch_report_<timestamp>.csv` containing all historic monitoring records.

---

## 👥 Team Division & Collaboration Workflow

### Suggested 2-Member Division:
- **Member 1 (Backend & SRE Focus):**
  - Monitoring engine, HTTP probing with timeout/retry logic (`app.py`).
  - SQLite database schema, indexing, and parameterized query security.
  - Mathematical calculations for availability, latency, and estimated downtime.
  - Automated test suite (`tests/test_pulsewatch.py`).
- **Member 2 (Frontend & DevOps Presentation Focus):**
  - Dark-mode DevOps dashboard layout (`templates/index.html`, `static/style.css`).
  - Real-time reactive data polling, Chart.js integrations, and state controller (`static/app.js`).
  - Quick demo preset buttons and SLA methodology modal.
  - CSV export UX, presentation slides, and live demonstration script.

### Git Branching Strategy:
To collaborate seamlessly without overwriting each other's work:

```bash
# 1. Clone repository
git clone <repository_url>
cd PulseWatch

# 2. Member 1 creates backend feature branch
git checkout -b feature/backend-engine
# Work on app.py and tests...
git add app.py tests/
git commit -m "feat(backend): implement health check engine and SLA calculations"
git push origin feature/backend-engine

# 3. Member 2 creates frontend feature branch
git checkout -b feature/frontend-ui
# Work on templates/ and static/...
git add templates/ static/
git commit -m "feat(ui): build dark DevOps dashboard with Chart.js analytics"
git push origin feature/frontend-ui

# 4. Merging back to main via Pull Requests (or local merge)
git checkout main
git pull origin main
git merge --no-ff feature/backend-engine
git merge --no-ff feature/frontend-ui
git push origin main
```

---

## 🔒 Security Considerations

1. **SSRF Boundary:** The server strictly disallows monitoring internal IP addresses (`127.0.0.1`, RFC 1918 private subnets, cloud metadata `169.254.169.254`). For explicit offline local testing during hackathons, set `PULSEWATCH_ALLOW_PRIVATE_IPS=1`.
2. **SQL Injection Defense:** All queries to the SQLite database use parameterized SQL queries (`?` place-holders) rather than string concatenation.
3. **No Hardcoded Secrets:** Configuration keys and secrets are loaded from environment variables.
4. **Production Debug Mode:** Flask debug mode is disabled (`debug=False`) by default.

---

## ☁️ Public Deployment Guide

When hackathon organizers require public accessibility, prefer reliable platforms that **do not require payment-card verification**:

### Option 1: Render.com (Recommended Free Cloud Hosting - No Card Required)
1. Sign up for a free account at [render.com](https://render.com) using GitHub.
2. Push your `PulseWatch` repository to GitHub.
3. Create a **New Web Service** and select your repository.
4. Set Build Command: `pip install -r requirements.txt`
5. Set Start Command: `python app.py` (or `gunicorn app:app` by adding `gunicorn` to requirements).
6. Set Environment Variables:
   - `PORT`: `5000`
   - `PULSEWATCH_ALLOW_PRIVATE_IPS`: `false`
7. Click **Create Web Service**. Render provides a free `https://<service-name>.onrender.com` public URL.
*Note: Render free tier services spin down after 15 minutes of inactivity and take ~45s to wake up on the first request.*

### Option 2: PythonAnywhere (No Card Required)
1. Sign up for a free Beginner account at [pythonanywhere.com](https://www.pythonanywhere.com).
2. Upload the `PulseWatch` directory or `git clone` from Bash console.
3. Configure a Flask Web App pointing to `app.py`.
4. Your dashboard will be publicly hosted at `https://<username>.pythonanywhere.com`.

### Option 3: Approved Temporary HTTPS Tunnel (Cloudflare Tunnel / ngrok)
If the hackathon allows temporary HTTPS tunnels for live judging:
1. Run PulseWatch locally: `python app.py`
2. In a separate terminal, run Cloudflare Tunnel:
   ```bash
   cloudflared tunnel --url http://127.0.0.1:5000
   ```
   *(Or with ngrok: `ngrok http 5000`)*
3. Share the generated temporary `https://*.trycloudflare.com` URL with judges.
*Note: Explain to judges that tunnels are temporary local proxies, not permanent cloud deployments.*

---

## ⏱️ 5-Minute Hackathon Demonstration Script

1. **Minute 1 — Problem & Introduction:**  
   - "Good morning judges! We are presenting **PulseWatch**, our solution for Problem 20: Service Availability and SLA Reporter. We built a lightweight, zero-cloud-cost monitoring solution for microservices."
2. **Minute 2 — Dashboard Walkthrough:**  
   - "Notice the modern DevOps dark theme with real-time indicators. Our KPI cards highlight Availability SLA %, Average Latency in ms, and Estimated Downtime."
3. **Minute 3 — Live Healthy Demo:**  
   - Click the quick preset **🟢 200 OK (Healthy)**. Click **Check Now**.  
   - Show the green UP badge in the audit table, the response time graph update, and the SLA staying at 100%.
4. **Minute 4 — Outage Simulation & Downtime Calculation:**  
   - Click the quick preset **🔴 500 Server Error** (or enter an invalid endpoint).  
   - Trigger 2 checks. Show the immediate status change to **DOWN**, the SLA drop, and point to the **Estimated Downtime card**.  
   - Explain to the judges: *"We calculate interval-sampled downtime as failed checks multiplied by the 10s interval. We distinguish sampled estimates from physical continuous outage duration."*
5. **Minute 5 — CSV Audit Export & Conclusion:**  
   - Click **Export CSV**. Open the downloaded CSV file in Excel/Notepad to demonstrate compliance-ready timestamped logs.  
   - Highlight the 16 automated passing unit tests and clean code architecture.

---

## 📜 License
Developed for the **BIT DevOps Community Hackathon 2026**. Open source under the MIT License.
