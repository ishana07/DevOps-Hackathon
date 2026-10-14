/**
 * PulseWatch — Service Availability and SLA Reporter
 * Vanilla JavaScript Frontend Controller
 * BIT DevOps Community Hackathon 2026
 */

document.addEventListener('DOMContentLoaded', () => {
  // ---------------------------------------------------------------------------
  // State Management
  // ---------------------------------------------------------------------------
  const state = {
    config: {
      endpoint: '',
      interval_seconds: 10,
      monitoring_enabled: true,
      allow_private_ips: false
    },
    stats: {},
    history: [],
    currentFilter: 'ALL',
    isChecking: false,
    pollTimer: null,
    latencyChart: null,
    doughnutChart: null
  };

  // ---------------------------------------------------------------------------
  // DOM Elements
  // ---------------------------------------------------------------------------
  const elements = {
    // Clock & Status
    utcClock: document.getElementById('utc-clock'),
    liveStatusText: document.getElementById('live-status-text'),
    liveStatusIndicator: document.getElementById('live-status-indicator'),
    
    // KPI Cards
    kpiAvailability: document.getElementById('kpi-availability'),
    kpiSlaTier: document.getElementById('kpi-sla-tier'),
    kpiAvailabilityTrend: document.getElementById('kpi-availability-trend'),
    kpiProgressFill: document.getElementById('kpi-progress-fill'),
    kpiLatency: document.getElementById('kpi-latency'),
    kpiMinLatency: document.getElementById('kpi-min-latency'),
    kpiMaxLatency: document.getElementById('kpi-max-latency'),
    kpiDowntime: document.getElementById('kpi-downtime'),
    kpiObservedOutage: document.getElementById('kpi-observed-outage'),
    kpiTotalChecks: document.getElementById('kpi-total-checks'),
    kpiPassedChecks: document.getElementById('kpi-passed-checks'),
    kpiFailedChecks: document.getElementById('kpi-failed-checks'),
    slaRangeLabel: document.getElementById('sla-range-label'),
    slaPeriodText: document.getElementById('sla-period-text'),
    
    // Controls
    configForm: document.getElementById('config-form'),
    endpointInput: document.getElementById('endpoint-input'),
    intervalSelect: document.getElementById('interval-select'),
    saveConfigBtn: document.getElementById('save-config-btn'),
    checkNowBtn: document.getElementById('check-now-btn'),
    checkSpinner: document.getElementById('check-spinner'),
    checkIcon: document.getElementById('check-icon'),
    toggleMonitoringBtn: document.getElementById('toggle-monitoring-btn'),
    toggleMonitorIcon: document.getElementById('toggle-monitor-icon'),
    toggleMonitorText: document.getElementById('toggle-monitor-text'),
    clearHistoryBtn: document.getElementById('clear-history-btn'),
    
    // Charts
    chartLatestLatency: document.getElementById('chart-latest-latency'),
    doughnutPct: document.getElementById('doughnut-pct'),
    
    // Table & Filters
    historyTableBody: document.getElementById('history-table-body'),
    countAll: document.getElementById('count-all'),
    countUp: document.getElementById('count-up'),
    countDown: document.getElementById('count-down'),
    filterBtns: document.querySelectorAll('.filter-btn'),
    presetBtns: document.querySelectorAll('.preset-btn'),
    
    // Modal & Toast
    methodologyModal: document.getElementById('methodology-modal'),
    openMethodologyBtn: document.getElementById('open-methodology-btn'),
    downtimeInfoBtn: document.getElementById('downtime-info-btn'),
    closeModalBtn: document.getElementById('close-modal-btn'),
    modalAckBtn: document.getElementById('modal-ack-btn'),
    toastContainer: document.getElementById('toast-container')
  };

  // ---------------------------------------------------------------------------
  // UTC Clock
  // ---------------------------------------------------------------------------
  function updateUtcClock() {
    const now = new Date();
    elements.utcClock.textContent = `UTC ${now.toISOString().substring(11, 19)}`;
  }
  setInterval(updateUtcClock, 1000);
  updateUtcClock();

  // ---------------------------------------------------------------------------
  // Toast Notifications
  // ---------------------------------------------------------------------------
  function showToast(message, type = 'info', duration = 3500) {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    const icon = type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️';
    toast.innerHTML = `<span>${icon}</span> <span>${escapeHtml(message)}</span>`;
    
    elements.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ---------------------------------------------------------------------------
  // Chart.js Initialization
  // ---------------------------------------------------------------------------
  function initCharts() {
    const ctxLatency = document.getElementById('latencyChart').getContext('2d');
    
    // Line chart gradient
    const gradient = ctxLatency.createLinearGradient(0, 0, 0, 240);
    gradient.addColorStop(0, 'rgba(99, 102, 241, 0.45)');
    gradient.addColorStop(1, 'rgba(99, 102, 241, 0.0)');

    state.latencyChart = new Chart(ctxLatency, {
      type: 'line',
      data: {
        labels: [],
        datasets: [{
          label: 'Latency (ms)',
          data: [],
          borderColor: '#6366F1',
          borderWidth: 2,
          backgroundColor: gradient,
          fill: true,
          tension: 0.3,
          pointBackgroundColor: '#8B5CF6',
          pointBorderColor: '#fff',
          pointRadius: 3,
          pointHoverRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#1E293B',
            titleColor: '#9CA3AF',
            bodyColor: '#F3F4F6',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1,
            displayColors: false,
            callbacks: {
              label: (context) => `Latency: ${context.parsed.y} ms`
            }
          }
        },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.04)' },
            ticks: { color: '#6B7280', font: { family: 'JetBrains Mono', size: 10 } }
          },
          y: {
            beginAtZero: true,
            grid: { color: 'rgba(255, 255, 255, 0.04)' },
            ticks: { color: '#6B7280', font: { family: 'JetBrains Mono', size: 10 } }
          }
        }
      }
    });

    const ctxDoughnut = document.getElementById('uptimeDoughnutChart').getContext('2d');
    state.doughnutChart = new Chart(ctxDoughnut, {
      type: 'doughnut',
      data: {
        labels: ['UP (2xx)', 'DOWN (Failures)'],
        datasets: [{
          data: [1, 0],
          backgroundColor: ['#10B981', '#EF4444'],
          borderColor: '#151E32',
          borderWidth: 3,
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '76%',
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              color: '#9CA3AF',
              font: { family: 'Inter', size: 11 },
              boxWidth: 12
            }
          },
          tooltip: {
            backgroundColor: '#1E293B',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1
          }
        }
      }
    });
  }

  // ---------------------------------------------------------------------------
  // Data Fetching & Sync
  // ---------------------------------------------------------------------------
  async function fetchConfig() {
    try {
      const res = await fetch('/api/config');
      if (!res.ok) throw new Error('Failed to retrieve configuration');
      const cfg = await res.json();
      state.config = cfg;
      
      elements.endpointInput.value = cfg.endpoint || '';
      elements.intervalSelect.value = String(cfg.interval_seconds || 10);
      updateMonitoringButtonState(cfg.monitoring_enabled);
    } catch (err) {
      console.error(err);
      showToast('Could not load configuration', 'error');
    }
  }

  async function fetchStats() {
    try {
      const res = await fetch('/api/stats');
      if (!res.ok) throw new Error('Failed to retrieve stats');
      const stats = await res.json();
      state.stats = stats;
      renderStats(stats);
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchHistory() {
    try {
      const statusParam = state.currentFilter === 'ALL' ? '' : `&status=${state.currentFilter}`;
      const res = await fetch(`/api/history?limit=100${statusParam}`);
      if (!res.ok) throw new Error('Failed to retrieve history');
      const data = await res.json();
      state.history = data.history || [];
      renderHistoryTable(state.history);
      updateCharts(data.history || []);
    } catch (err) {
      console.error(err);
    }
  }

  // ---------------------------------------------------------------------------
  // Renderers
  // ---------------------------------------------------------------------------
  function renderStats(s) {
    if (!s) return;

    // Availability
    elements.kpiAvailability.textContent = `${s.availability_percentage}%`;
    elements.kpiSlaTier.textContent = s.sla_tier || 'SLA';
    elements.kpiProgressFill.style.width = `${Math.min(100, Math.max(0, s.availability_percentage))}%`;
    
    if (elements.kpiAvailabilityTrend) {
      elements.kpiAvailabilityTrend.textContent = s.total_checks > 0
        ? `${s.successful_checks}/${s.total_checks} UP (${s.availability_percentage}%)`
        : 'Target: 99.9%';
    }

    // SLA Formula Section Info
    if (elements.slaRangeLabel) {
      elements.slaRangeLabel.textContent = `Record Range: ${s.record_range || 'All Samples'}`;
    }
    if (elements.slaPeriodText) {
      elements.slaPeriodText.textContent = s.reporting_period || 'All Recorded History';
    }

    // Latency
    elements.kpiLatency.textContent = s.average_response_time_ms ? `${s.average_response_time_ms} ms` : '-- ms';
    elements.kpiMinLatency.textContent = s.min_response_time_ms ? `${s.min_response_time_ms} ms` : '--';
    elements.kpiMaxLatency.textContent = s.max_response_time_ms ? `${s.max_response_time_ms} ms` : '--';

    // Downtime
    elements.kpiDowntime.textContent = s.estimated_downtime_formatted || '0s';
    elements.kpiObservedOutage.textContent = s.observed_outage_formatted || '0s';

    // Counts
    elements.kpiTotalChecks.textContent = s.total_checks;
    elements.kpiPassedChecks.textContent = s.successful_checks;
    elements.kpiFailedChecks.textContent = s.failed_checks;
    elements.countAll.textContent = s.total_checks;
    elements.countUp.textContent = s.successful_checks;
    elements.countDown.textContent = s.failed_checks;

    // Header Live Status Badge
    const dot = elements.liveStatusIndicator.querySelector('.status-dot');
    dot.className = 'status-dot';
    
    if (!state.config.monitoring_enabled) {
      dot.classList.add('paused');
      elements.liveStatusText.textContent = 'MONITORING PAUSED';
    } else if (s.current_status === 'UP') {
      dot.classList.add('up', 'ping-animation');
      elements.liveStatusText.textContent = 'SERVICE OPERATIONAL (UP)';
    } else if (s.current_status === 'DOWN') {
      dot.classList.add('down', 'ping-animation');
      elements.liveStatusText.textContent = 'SERVICE OUTAGE (DOWN)';
    } else {
      elements.liveStatusText.textContent = 'STANDBY';
    }

    // Doughnut center text
    elements.doughnutPct.textContent = `${s.availability_percentage}%`;
    
    // Doughnut chart update
    if (state.doughnutChart) {
      const up = s.successful_checks;
      const down = s.failed_checks;
      state.doughnutChart.data.datasets[0].data = (up === 0 && down === 0) ? [1, 0] : [up, down];
      state.doughnutChart.update();
    }
  }

  function updateCharts(history) {
    if (!state.latencyChart) return;

    // Take the last 30 checks in chronological order (oldest to newest)
    const chronological = [...history].reverse().slice(-30);
    const labels = chronological.map(c => {
      const t = c.timestamp.split('T')[1] || c.timestamp;
      return t.substring(0, 8);
    });
    const latencies = chronological.map(c => c.response_time_ms !== null ? c.response_time_ms : 0);

    state.latencyChart.data.labels = labels;
    state.latencyChart.data.datasets[0].data = latencies;
    state.latencyChart.update();

    if (chronological.length > 0) {
      const last = chronological[chronological.length - 1];
      elements.chartLatestLatency.textContent = last.response_time_ms !== null ? `${last.response_time_ms} ms` : 'N/A';
    }
  }

  function renderHistoryTable(rows) {
    elements.historyTableBody.innerHTML = '';
    
    if (!rows || rows.length === 0) {
      elements.historyTableBody.innerHTML = `
        <tr class="empty-row">
          <td colspan="8">
            <div class="empty-state">
              <span class="empty-icon">📡</span>
              <p>No health checks recorded matching filter.</p>
            </div>
          </td>
        </tr>`;
      return;
    }

    const fragment = document.createDocumentFragment();
    rows.forEach(r => {
      const tr = document.createElement('tr');
      const isUp = r.status === 'UP';
      const statusBadge = isUp 
        ? `<span class="status-badge up">🟢 UP</span>` 
        : `<span class="status-badge down">🔴 DOWN</span>`;
      
      const codeBadge = r.status_code 
        ? `<span class="font-mono ${r.status_code < 300 ? 'text-success' : 'text-danger'}">${r.status_code}</span>` 
        : `<span class="text-muted">—</span>`;
      
      const latencyStr = r.response_time_ms !== null 
        ? `<span class="font-mono">${r.response_time_ms} ms</span>` 
        : `<span class="text-muted">—</span>`;

      const detailsStr = r.error_message 
        ? `<span class="text-danger" title="${escapeHtml(r.error_message)}">${escapeHtml(r.error_message.substring(0, 45))}${r.error_message.length > 45 ? '...' : ''}</span>` 
        : `<span class="text-success">2xx OK</span>`;

      tr.innerHTML = `
        <td class="font-mono text-muted">#${r.id}</td>
        <td class="font-mono">${escapeHtml(r.timestamp)}</td>
        <td class="font-mono" title="${escapeHtml(r.endpoint)}">${escapeHtml(r.endpoint.length > 35 ? r.endpoint.substring(0, 32) + '...' : r.endpoint)}</td>
        <td>${statusBadge}</td>
        <td>${codeBadge}</td>
        <td>${latencyStr}</td>
        <td>${detailsStr}</td>
        <td><span class="type-pill">${escapeHtml(r.check_type)}</span></td>
      `;
      fragment.appendChild(tr);
    });

    elements.historyTableBody.appendChild(fragment);
  }

  function updateMonitoringButtonState(enabled) {
    state.config.monitoring_enabled = enabled;
    if (enabled) {
      elements.toggleMonitorIcon.textContent = '⏸';
      elements.toggleMonitorText.textContent = 'Pause Monitor';
      elements.toggleMonitoringBtn.classList.remove('btn-danger-outline');
      elements.toggleMonitoringBtn.classList.add('btn-outline');
    } else {
      elements.toggleMonitorIcon.textContent = '▶';
      elements.toggleMonitorText.textContent = 'Resume Monitor';
      elements.toggleMonitoringBtn.classList.remove('btn-outline');
      elements.toggleMonitoringBtn.classList.add('btn-danger-outline');
    }
  }

  // ---------------------------------------------------------------------------
  // Action Handlers
  // ---------------------------------------------------------------------------
  // 1. Manual Check Now
  elements.checkNowBtn.addEventListener('click', async () => {
    if (state.isChecking) return;
    state.isChecking = true;
    elements.checkSpinner.style.display = 'inline-block';
    elements.checkIcon.style.display = 'none';
    elements.checkNowBtn.disabled = true;

    try {
      const targetEndpoint = elements.endpointInput.value.trim();
      const res = await fetch('/api/check-now', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(targetEndpoint ? { endpoint: targetEndpoint } : {})
      });
      const data = await res.json();
      
      if (!res.ok) {
        throw new Error(data.error || 'Check failed');
      }

      const c = data.check;
      if (c.status === 'UP') {
        showToast(`Health Check UP: ${c.status_code || 200} OK (${c.response_time_ms} ms)`, 'success');
      } else {
        showToast(`Health Check DOWN: ${c.error_message || 'Service failure'}`, 'error');
      }

      await fetchStats();
      await fetchHistory();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      state.isChecking = false;
      elements.checkSpinner.style.display = 'none';
      elements.checkIcon.style.display = 'inline-block';
      elements.checkNowBtn.disabled = false;
    }
  });

  // 2. Save Configuration
  elements.configForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const endpoint = elements.endpointInput.value.trim();
    const interval_seconds = parseInt(elements.intervalSelect.value, 10);

    if (!endpoint) {
      showToast('Endpoint URL is required', 'error');
      return;
    }

    elements.saveConfigBtn.disabled = true;
    elements.saveConfigBtn.textContent = 'Saving...';

    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint, interval_seconds })
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || 'Failed to update configuration');
      }

      showToast('Configuration updated successfully!', 'success');
      state.config = data.config;
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      elements.saveConfigBtn.disabled = false;
      elements.saveConfigBtn.textContent = 'Save & Apply';
    }
  });

  // 3. Toggle Monitoring Active / Paused
  elements.toggleMonitoringBtn.addEventListener('click', async () => {
    const newState = !state.config.monitoring_enabled;
    try {
      const res = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ monitoring_enabled: newState })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Failed to toggle');
      
      updateMonitoringButtonState(newState);
      showToast(newState ? 'Periodic monitoring resumed' : 'Periodic monitoring paused', 'info');
      fetchStats();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  // 4. Quick Demo Presets
  elements.presetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const presetUrl = btn.getAttribute('data-url');
      if (presetUrl.startsWith('/')) {
        // Resolve relative mock URLs to current host
        elements.endpointInput.value = `${window.location.origin}${presetUrl}`;
      } else {
        elements.endpointInput.value = presetUrl;
      }
      showToast(`Selected demo preset: ${btn.textContent.trim()}`, 'info');
    });
  });

  // 5. Filter Buttons (All, UP, DOWN)
  elements.filterBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      elements.filterBtns.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.currentFilter = btn.getAttribute('data-filter');
      fetchHistory();
    });
  });

  // 6. Clear History Logs
  elements.clearHistoryBtn.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to clear all health check history logs? This is useful for starting a clean hackathon demo.')) {
      return;
    }

    try {
      const res = await fetch('/api/reset-data', { method: 'POST' });
      if (!res.ok) throw new Error('Failed to reset data');
      showToast('Health check history cleared', 'info');
      await fetchStats();
      await fetchHistory();
    } catch (err) {
      showToast(err.message, 'error');
    }
  });

  // 7. Modal Controls
  function openModal() {
    elements.methodologyModal.style.display = 'flex';
  }
  function closeModal() {
    elements.methodologyModal.style.display = 'none';
  }

  elements.openMethodologyBtn.addEventListener('click', openModal);
  elements.downtimeInfoBtn.addEventListener('click', openModal);
  elements.closeModalBtn.addEventListener('click', closeModal);
  elements.modalAckBtn.addEventListener('click', closeModal);
  elements.methodologyModal.addEventListener('click', (e) => {
    if (e.target === elements.methodologyModal) closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && elements.methodologyModal.style.display === 'flex') {
      closeModal();
    }
  });

  // ---------------------------------------------------------------------------
  // Polling Loop & App Initialization
  // ---------------------------------------------------------------------------
  async function initialize() {
    initCharts();
    await fetchConfig();
    await fetchStats();
    await fetchHistory();

    // Auto-poll stats & history every 3.5 seconds
    state.pollTimer = setInterval(async () => {
      await fetchStats();
      await fetchHistory();
    }, 3500);
  }

  initialize();
});
