/* ═══════════════════════════════════════════════════════════════
   main.js – Bambusleitung Frontend Logic
   SocketIO + REST API + Chart.js + Live Updates + Auth
═══════════════════════════════════════════════════════════════ */

// ─── Auth ─────────────────────────────────────────────────────
async function checkAuth() {
  try {
    const r = await fetch('/api/auth/status');
    const data = await r.json();
    if (data.auth_required && !data.authenticated) {
      showLoginOverlay();
    } else {
      hideLoginOverlay();
      if (data.auth_required) {
        document.getElementById('logoutBtn').style.display = 'inline-flex';
      }
    }
  } catch (e) {
    console.error('Auth-Status konnte nicht geladen werden:', e);
  }
}

function showLoginOverlay() {
  document.getElementById('loginOverlay').style.display = 'flex';
  setTimeout(() => document.getElementById('loginPassword').focus(), 100);
}

function hideLoginOverlay() {
  document.getElementById('loginOverlay').style.display = 'none';
}

async function submitLogin() {
  const btn = document.getElementById('loginBtn');
  const errEl = document.getElementById('loginError');
  const password = document.getElementById('loginPassword').value;

  btn.disabled = true;
  document.getElementById('loginBtnText').textContent = '⏳ Wird geprüft...';
  errEl.style.display = 'none';

  try {
    const r = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    const data = await r.json();
    if (data.success) {
      hideLoginOverlay();
      document.getElementById('logoutBtn').style.display = 'inline-flex';
      document.getElementById('loginPassword').value = '';
      // Dashboard laden
      loadConfig();
      loadHistory();
      socket.connect();
    } else {
      errEl.textContent = data.error || 'Falsches Passwort';
      errEl.style.display = 'block';
      document.getElementById('loginPassword').select();
    }
  } catch (e) {
    errEl.textContent = 'Verbindungsfehler';
    errEl.style.display = 'block';
  } finally {
    btn.disabled = false;
    document.getElementById('loginBtnText').textContent = '🔓 Anmelden';
  }
}

async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  socket.disconnect();
  document.getElementById('logoutBtn').style.display = 'none';
  showLoginOverlay();
  toast('👋 Abgemeldet', 'info');
}

function togglePasswordVisibility() {
  const input = document.getElementById('loginPassword');
  input.type = input.type === 'password' ? 'text' : 'password';
}

// ─── State ────────────────────────────────────────────────────
let config = {};
let history = [];
let speedChart = null;
let isTestRunning = false;
let currentDownload = null;
let currentUpload = null;

// ─── SocketIO ─────────────────────────────────────────────────
const socket = io({ transports: ['websocket', 'polling'] });

socket.on('connect', () => {
  setGlobalStatus('connected', 'Verbunden');
  loadConfig();
  loadHistory();
});

socket.on('disconnect', () => {
  setGlobalStatus('error', 'Verbindung verloren');
});

socket.on('status', (data) => {
  updateRunningState(data.running, data.run_type);
  updateNextRun(data.next_run);
});

socket.on('test_started', (data) => {
  isTestRunning = true;
  currentDownload = null;
  currentUpload = null;
  updateRunningState(true, data.run_type);
  showLiveSection(true, data.run_type);
  setRunBtn(false);
  hideElement('liveIdle');
  hideElement('liveError');
  setGlobalStatus('running', `Test läuft (${data.run_type === 'manual' ? 'Manuell' : 'Auto'})`);
  toast(`🚀 Test gestartet → ${data.target}`, 'info');
});

socket.on('live_data', (data) => {
  if (data.error) {
    showLiveError(data.error);
    return;
  }
  if (data.direction === 'download') {
    currentDownload = data;
    updateMeter('dl', data.bandwidth_mbps);
    updateLiveDetails(data);
  } else if (data.direction === 'upload') {
    currentUpload = data;
    updateMeter('ul', data.bandwidth_mbps);
  }
});

socket.on('test_finished', (data) => {
  isTestRunning = false;
  updateRunningState(false, 'none');
  setRunBtn(true);
  setGlobalStatus('connected', 'Verbunden');

  const dl = data.download_mbps;
  const ul = data.upload_mbps;

  if (data.status === 'success') {
    toast(`✅ Test abgeschlossen  ⬇${fmt(dl)} / ⬆${fmt(ul)} Mbit/s`, 'success');
    // Finale Werte anzeigen
    if (dl !== null) updateMeter('dl', dl);
    if (ul !== null) updateMeter('ul', ul);
  } else {
    toast(`❌ Test fehlgeschlagen: ${data.error_msg || 'Unbekannter Fehler'}`, 'error');
    showLiveError(data.error_msg);
  }

  // Live-Badge ausblenden nach kurzer Pause
  setTimeout(() => {
    showLiveSection(false, null);
  }, 4000);
});

socket.on('history_update', (entry) => {
  // Neuen Eintrag an den Anfang der Liste setzen
  history.unshift(entry);
  renderHistoryTable();
  updateChart();
});

socket.on('config_update', (cfg) => {
  config = cfg;
  renderConfig();
  updateNextRun(cfg.next_run);
});

socket.on('scheduler_skip', (data) => {
  toast(`⏭ Automatischer Test übersprungen: ${data.reason}`, 'warn');
});

// ─── Config ───────────────────────────────────────────────────
async function loadConfig() {
  try {
    const r = await fetch('/api/config');
    config = await r.json();
    renderConfig();
    updateNextRun(config.next_run);
    updateRunTargetBadge();
  } catch (e) {
    console.error('Config laden fehlgeschlagen:', e);
  }
}

function renderConfig() {
  setValue('targetIp', config.target_ip || '');
  setValue('targetPort', config.target_port || 5201);
  setValue('intervalMin', config.interval_minutes || 60);
  setValue('testDuration', config.test_duration || 10);
  setValue('iperfParams', config.iperf_params || '');
  setToggle(config.enabled || false);
  updateRunTargetBadge();
}

async function saveConfig() {
  const btn = document.getElementById('saveConfigBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="btn-icon">⏳</span> Speichern...';

  const payload = {
    target_ip: getValue('targetIp').trim(),
    target_port: parseInt(getValue('targetPort')) || 5201,
    interval_minutes: parseInt(getValue('intervalMin')) || 60,
    test_duration: parseInt(getValue('testDuration')) || 10,
    iperf_params: getValue('iperfParams').trim(),
    enabled: document.getElementById('enableToggle').checked,
  };

  try {
    const r = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    config = await r.json();
    renderConfig();
    updateNextRun(config.next_run);
    toast('✅ Konfiguration gespeichert', 'success');
  } catch (e) {
    toast('❌ Fehler beim Speichern', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">💾</span> Speichern';
  }
}

// ─── Manual Run ───────────────────────────────────────────────
async function startManualTest() {
  const btn = document.getElementById('runBtn');
  btn.disabled = true;

  const msgEl = document.getElementById('runStatusMsg');
  msgEl.textContent = '';
  msgEl.className = 'run-status-msg';

  try {
    const r = await fetch('/api/run', { method: 'POST' });
    const data = await r.json();

    if (!r.ok || !data.success) {
      const msg = data.error || 'Fehler beim Starten';
      msgEl.textContent = msg;
      msgEl.className = 'run-status-msg error';
      toast(`⚠️ ${msg}`, 'error');
      btn.disabled = false;
    } else {
      msgEl.textContent = data.message || 'Test startet...';
      msgEl.className = 'run-status-msg success';
    }
  } catch (e) {
    msgEl.textContent = 'Verbindungsfehler';
    msgEl.className = 'run-status-msg error';
    btn.disabled = false;
  }
}

// ─── History ──────────────────────────────────────────────────
async function loadHistory() {
  try {
    const r = await fetch('/api/history?limit=200');
    history = await r.json();
    renderHistoryTable();
    initChart();
  } catch (e) {
    console.error('History laden fehlgeschlagen:', e);
  }
}

function renderHistoryTable() {
  const tbody = document.getElementById('historyBody');
  if (!history.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="table-empty">Noch keine Tests vorhanden</td></tr>';
    return;
  }

  tbody.innerHTML = history.map(r => {
    const ts = r.timestamp ? new Date(r.timestamp + 'Z').toLocaleString('de-DE') : '–';
    const dl = r.download_mbps !== null && r.download_mbps !== undefined ? fmt(r.download_mbps) : '–';
    const ul = r.upload_mbps  !== null && r.upload_mbps  !== undefined ? fmt(r.upload_mbps)  : '–';
    const jitter = r.jitter_ms !== null && r.jitter_ms !== undefined ? r.jitter_ms.toFixed(2) + ' ms' : '–';
    const loss   = r.packet_loss_pct !== null && r.packet_loss_pct !== undefined ? r.packet_loss_pct.toFixed(1) + '%' : '–';
    const typeLabel = r.run_type === 'manual' ? 'Manuell' : 'Auto';
    const statusIcon = r.status === 'success' ? '✓' : '✗';

    return `
      <tr>
        <td>${ts}</td>
        <td><span class="badge-type ${r.run_type}">${typeLabel}</span></td>
        <td class="mono">${r.target_ip}:${r.target_port}</td>
        <td class="mono">${dl}</td>
        <td class="mono">${ul}</td>
        <td class="mono">${jitter}</td>
        <td class="mono">${loss}</td>
        <td><span class="badge-status ${r.status}">${statusIcon} ${r.status === 'success' ? 'OK' : 'Fehler'}</span></td>
      </tr>`;
  }).join('');
}

// ─── Chart ────────────────────────────────────────────────────
function initChart() {
  const ctx = document.getElementById('speedChart').getContext('2d');
  const chartData = buildChartData();

  if (speedChart) speedChart.destroy();

  speedChart = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [
        {
          label: 'Download (Mbit/s)',
          data: chartData.dl,
          borderColor: '#00e5a0',
          backgroundColor: 'rgba(0,229,160,0.08)',
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: '#00e5a0',
          tension: 0.4,
          fill: true,
        },
        {
          label: 'Upload (Mbit/s)',
          data: chartData.ul,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.07)',
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBackgroundColor: '#3b82f6',
          tension: 0.4,
          fill: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1e2a42',
          borderColor: 'rgba(255,255,255,0.1)',
          borderWidth: 1,
          titleColor: '#94a3b8',
          bodyColor: '#f1f5f9',
          callbacks: {
            label: ctx => ` ${ctx.dataset.label}: ${fmt(ctx.raw.y)} Mbit/s`,
          },
        },
      },
      scales: {
        x: {
          type: 'time',
          time: { tooltipFormat: 'dd.MM.yy HH:mm', displayFormats: { hour: 'HH:mm', day: 'dd.MM' } },
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { color: '#4b5563', maxTicksLimit: 10 },
        },
        y: {
          min: 0,
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            color: '#4b5563',
            callback: v => v + ' M',
          },
        },
      },
    },
  });
}

function buildChartData() {
  const successOnly = [...history].filter(r => r.status === 'success').reverse();
  return {
    dl: successOnly.map(r => ({ x: new Date(r.timestamp + 'Z'), y: r.download_mbps })).filter(p => p.y !== null),
    ul: successOnly.map(r => ({ x: new Date(r.timestamp + 'Z'), y: r.upload_mbps  })).filter(p => p.y !== null),
  };
}

function updateChart() {
  if (!speedChart) { initChart(); return; }
  const chartData = buildChartData();
  speedChart.data.datasets[0].data = chartData.dl;
  speedChart.data.datasets[1].data = chartData.ul;
  speedChart.update('active');
}

// ─── Excel Export ─────────────────────────────────────────────
function exportExcel() {
  toast('📥 Export wird vorbereitet...', 'info');
  window.location.href = '/api/export';
}

// ─── UI Helpers ───────────────────────────────────────────────
function setGlobalStatus(type, text) {
  const dot  = document.getElementById('statusDot');
  const span = document.getElementById('statusText');
  dot.className  = `status-dot ${type}`;
  span.textContent = text;
}

function updateRunningState(running, runType) {
  isTestRunning = running;
  setRunBtn(!running);
}

function setRunBtn(enabled) {
  const btn = document.getElementById('runBtn');
  btn.disabled = !enabled;
  if (!enabled && isTestRunning) {
    document.getElementById('runStatusMsg').textContent = 'Test läuft...';
    document.getElementById('runStatusMsg').className = 'run-status-msg';
  }
}

function showLiveSection(active, runType) {
  const badge    = document.getElementById('liveBadge');
  const typeBadge = document.getElementById('testTypeBadge');
  const idle     = document.getElementById('liveIdle');

  if (active) {
    badge.style.display = 'inline-block';
    typeBadge.style.display = 'inline-block';
    typeBadge.className = `test-type-badge ${runType}`;
    typeBadge.textContent = runType === 'manual' ? '🖱 Manuell' : '⏰ Automatisch';
    idle.style.display = 'none';
    // Meter aktivieren
    document.querySelectorAll('.meter-card').forEach(c => c.classList.add('active'));
  } else {
    badge.style.display = 'none';
    typeBadge.style.display = 'none';
    idle.style.display = 'flex';
    document.querySelectorAll('.meter-card').forEach(c => c.classList.remove('active'));
  }
}

function updateMeter(dir, mbps) {
  const valEl = document.getElementById(dir === 'dl' ? 'dlValue' : 'ulValue');
  const barEl = document.getElementById(dir === 'dl' ? 'dlBar' : 'ulBar');
  if (mbps === null || mbps === undefined) return;
  valEl.textContent = fmt(mbps);
  // Bar: skaliert auf 1000 Mbit/s als 100%
  const pct = Math.min(100, (mbps / 1000) * 100);
  barEl.style.width = pct + '%';
}

function updateLiveDetails(data) {
  setText('liveJitter',      data.jitter_ms     !== null ? data.jitter_ms?.toFixed(2) + ' ms' : '–');
  setText('liveLoss',        data.packet_loss_pct !== null ? data.packet_loss_pct?.toFixed(1) + '%' : '–');
  setText('liveDuration',    data.duration_s     !== null ? data.duration_s?.toFixed(1) + ' s' : '–');
  setText('liveRetransmits', data.retransmits     !== null && data.retransmits !== undefined ? data.retransmits : '–');
}

function showLiveError(msg) {
  const el = document.getElementById('liveError');
  el.textContent = `⚠️ ${msg}`;
  el.style.display = 'block';
}

function updateRunTargetBadge() {
  const el = document.getElementById('runTarget');
  const btn = document.getElementById('runBtn');
  const ip = config.target_ip || '';
  const port = config.target_port || 5201;
  if (ip) {
    el.textContent = `${ip}:${port}`;
    if (!isTestRunning) btn.disabled = false;
  } else {
    el.textContent = 'Kein Ziel konfiguriert';
    btn.disabled = true;
  }
}

function updateNextRun(nextRun) {
  const badge = document.getElementById('nextRunBadge');
  const text  = document.getElementById('nextRunText');
  if (nextRun && config.enabled) {
    badge.style.display = 'flex';
    const d = new Date(nextRun);
    text.textContent = `Nächster Test: ${d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })}`;
  } else {
    badge.style.display = 'none';
  }
}

function setToggle(enabled) {
  const track = document.getElementById('toggleTrack');
  const input = document.getElementById('enableToggle');
  const state = document.getElementById('toggleState');
  input.checked = enabled;
  if (enabled) {
    track.classList.add('active');
    state.textContent = 'Aktiviert';
    state.className = 'toggle-state active';
  } else {
    track.classList.remove('active');
    state.textContent = 'Deaktiviert';
    state.className = 'toggle-state';
  }
}

// Toggle-Click
document.getElementById('toggleTrack').addEventListener('click', function() {
  const input = document.getElementById('enableToggle');
  input.checked = !input.checked;
  setToggle(input.checked);
});

// ─── Helpers ──────────────────────────────────────────────────
function fmt(v) {
  if (v === null || v === undefined) return '–';
  return parseFloat(v).toFixed(1);
}

function getValue(id) { return document.getElementById(id).value; }
function setValue(id, val) { document.getElementById(id).value = val; }
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function hideElement(id) { const el = document.getElementById(id); if (el) el.style.display = 'none'; }

// ─── Toast ────────────────────────────────────────────────────
function toast(msg, type = 'info', duration = 4000) {
  const icons = { success: '✅', error: '❌', info: 'ℹ️', warn: '⚠️' };
  const container = document.getElementById('toastContainer');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-icon">${icons[type] || 'ℹ️'}</span><span class="toast-msg">${msg}</span>`;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = '0';
    setTimeout(() => el.remove(), 300);
  }, duration);
}

// ─── Init ─────────────────────────────────────────────────────
async function checkCurrentStatus() {
  try {
    const r = await fetch('/api/status');
    const data = await r.json();
    if (data.running) {
      isTestRunning = true;
      updateRunningState(true, data.run_type);
      showLiveSection(true, data.run_type);
      setGlobalStatus('running', `Test läuft (${data.run_type === 'manual' ? 'Manuell' : 'Auto'})`);
    }
    updateNextRun(data.next_run);
  } catch(e) {}
}

// Auth zuerst prüfen – lädt Dashboard nur wenn authentifiziert
checkAuth().then(() => {
  const overlay = document.getElementById('loginOverlay');
  if (overlay.style.display === 'none' || overlay.style.display === '') {
    checkCurrentStatus();
  }
});

