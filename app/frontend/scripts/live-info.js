/**
 * live-info.js - Runtime monitor view.
 */

const terminal = document.getElementById('terminal');
const statusElement = document.getElementById('connectionStatus');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const wifiInfoElement = document.getElementById('wifiInfo');
const serialInfoElement = document.getElementById('serialInfo');
const cameraInfoElement = document.getElementById('cameraInfo');

let pollInterval = null;
let lastSnapshot = null;

function addLog(message, type = 'info') {
  const line = document.createElement('div');
  line.className = 'terminal-line';

  const ts = document.createElement('span');
  ts.className = 'terminal-timestamp';
  ts.textContent = `[${new Date().toLocaleTimeString('en-US', { hour12: false })}] `;

  const text = document.createElement('span');
  text.className = `terminal-${type}`;
  text.textContent = message;

  line.appendChild(ts);
  line.appendChild(text);
  terminal.appendChild(line);

  while (terminal.children.length > 120) {
    terminal.removeChild(terminal.firstChild);
  }
  terminal.scrollTop = terminal.scrollHeight;
}

function updateStatus(state) {
  let statusClass = 'disconnected';
  let message = 'No Device Connected';

  if (state.connected) {
    statusClass = 'connected';
    message = `Connected (${state.active_source || 'unknown source'})`;
  }

  statusElement.className = `connection-status ${statusClass}`;
  statusDot.className = `status-dot ${statusClass}`;
  statusText.textContent = message;
}

function updatePanels(state) {
  const serial = state.serial || {};
  const wireless = state.wireless || {};
  const cursor = state.cursor || {};
  const serialAgent = (state.agent_stats || {}).serial || {};
  const cursorAgent = (state.agent_stats || {}).cursor || {};

  wifiInfoElement.innerHTML = `<strong>Wireless:</strong> ${wireless.connected ? 'Connected' : 'Disconnected'} | Device: ${wireless.device_id || 'N/A'} | Last Error: ${wireless.last_error || 'None'}`;
  serialInfoElement.innerHTML = `<strong>Serial:</strong> ${serial.connected ? 'Connected' : 'Disconnected'} | Port: ${serial.port || 'N/A'} | Mode: ${state.mode} | Serial Hz: ${serialAgent.loop_hz || 0}`;

  const lastSample = cursor.last_sample || {};
  cameraInfoElement.innerHTML =
    `<strong>Pipeline:</strong> Source: ${state.active_source || 'N/A'} | Sample Hz: ${cursor.sample_rate_hz || 0} | Queue Lag: ${cursor.queue_lag_ms || 'N/A'}ms | Last Sample: ${lastSample.x ?? 'N/A'}, ${lastSample.y ?? 'N/A'} | Cursor Agent Hz: ${cursorAgent.loop_hz || 0}`;
}

function logStateChanges(state) {
  if (!lastSnapshot) {
    addLog('Live monitor initialized', 'success');
  } else {
    if (lastSnapshot.connected !== state.connected) {
      addLog(state.connected ? 'Runtime connected' : 'Runtime disconnected', state.connected ? 'success' : 'warning');
    }
    if (lastSnapshot.active_source !== state.active_source) {
      addLog(`Active source changed: ${lastSnapshot.active_source || 'none'} -> ${state.active_source || 'none'}`, 'info');
    }
    if (lastSnapshot.last_error !== state.last_error && state.last_error) {
      addLog(`Runtime error: ${state.last_error}`, 'error');
    }
  }

  const events = state.events || [];
  if (events.length) {
    const latest = events[events.length - 1];
    if (!lastSnapshot || latest.ts_ms !== ((lastSnapshot.events || []).slice(-1)[0] || {}).ts_ms) {
      addLog(latest.message, 'warning');
    }
  }

  lastSnapshot = state;
}

async function pollRuntime() {
  try {
    const state = await window.eyeApi.getRuntimeState();
    updateStatus(state);
    updatePanels(state);
    logStateChanges(state);
  } catch (err) {
    statusElement.className = 'connection-status error';
    statusDot.className = 'status-dot error';
    statusText.textContent = 'Backend Connection Error';
    addLog(`Failed to fetch runtime state: ${err.message}`, 'error');
  }
}

function startPolling() {
  pollRuntime();
  pollInterval = setInterval(pollRuntime, 1000);
}

function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
}

document.getElementById('backBtn').addEventListener('click', () => {
  stopPolling();
  window.location.href = 'settings.html';
});

document.getElementById('deviceInfoBtn').addEventListener('click', async () => {
  try {
    const state = await window.eyeApi.getRuntimeState();
    alert(
      `Device Info:\n\n` +
      `Mode: ${state.mode}\n` +
      `Connected: ${state.connected ? 'Yes' : 'No'}\n` +
      `Active Source: ${state.active_source || 'N/A'}\n` +
      `Sample Rate: ${state.cursor.sample_rate_hz || 0} Hz\n` +
      `Queue Lag: ${state.cursor.queue_lag_ms || 'N/A'} ms\n` +
      `Last Error: ${state.last_error || 'None'}`
    );
  } catch (err) {
    alert('Unable to fetch device info');
  }
});

window.addEventListener('beforeunload', stopPolling);
startPolling();
