/**
 * settings.js - Settings page backed by Flask preferences/runtime state.
 */

let prefsState = null;

function applySettings(prefs, runtime) {
  const connectionMode = prefs.connection_method || runtime.mode || 'wifi';
  document.querySelectorAll('.mode-option').forEach((option) => {
    option.classList.toggle('active', option.dataset.mode === connectionMode);
  });

  const horizontal = Number(prefs.horizontal_sensitivity || 50);
  const vertical = Number(prefs.vertical_sensitivity || 50);

  document.getElementById('horizontalSensitivity').value = horizontal;
  document.getElementById('verticalSensitivity').value = vertical;
  document.getElementById('horizontalValue').textContent = String(horizontal);
  document.getElementById('verticalValue').textContent = String(vertical);
}

async function refresh() {
  const [prefs, runtime] = await Promise.all([
    window.eyeApi.getPrefs(),
    window.eyeApi.getRuntimeState(),
  ]);

  prefsState = prefs;
  applySettings(prefs, runtime);
}

async function saveSettings() {
  if (!prefsState) return;

  const activeModeElement = document.querySelector('.mode-option.active');
  const connectionMode = activeModeElement ? activeModeElement.dataset.mode : (prefsState.connection_method || 'wifi');
  const horizontalSensitivity = Number(document.getElementById('horizontalSensitivity').value);
  const verticalSensitivity = Number(document.getElementById('verticalSensitivity').value);

  prefsState = await window.eyeApi.updatePrefs({
    connection_method: connectionMode,
    horizontal_sensitivity: horizontalSensitivity,
    vertical_sensitivity: verticalSensitivity,
  });
}

document.getElementById('wifiMode').addEventListener('click', async function onWifiClick() {
  document.querySelectorAll('.mode-option').forEach((opt) => opt.classList.remove('active'));
  this.classList.add('active');
  await saveSettings();
});

document.getElementById('wiredMode').addEventListener('click', async function onWiredClick() {
  document.querySelectorAll('.mode-option').forEach((opt) => opt.classList.remove('active'));
  this.classList.add('active');
  await saveSettings();
});

document.getElementById('horizontalSensitivity').addEventListener('input', function onHorizontalInput() {
  document.getElementById('horizontalValue').textContent = this.value;
  saveSettings();
});

document.getElementById('verticalSensitivity').addEventListener('input', function onVerticalInput() {
  document.getElementById('verticalValue').textContent = this.value;
  saveSettings();
});

document.getElementById('recalibrateBtn').addEventListener('click', () => {
  window.location.href = 'calibration.html';
});

document.getElementById('advancedSettingsBtn').addEventListener('click', () => {
  window.location.href = 'advanced-settings.html';
});

document.getElementById('liveInfoBtn').addEventListener('click', () => {
  window.location.href = 'live-info.html';
});

document.getElementById('flashWifiBtn').addEventListener('click', () => {
  window.location.href = 'connect.html';
});

document.getElementById('deviceInfoBtn').addEventListener('click', async () => {
  try {
    const status = await window.eyeApi.getRuntimeState();
    alert(
      `Device Info:\n\n` +
      `Mode: ${status.mode}\n` +
      `Connected: ${status.connected ? 'Yes' : 'No'}\n` +
      `Active Source: ${status.active_source || 'N/A'}\n` +
      `Serial: ${status.serial.connected ? `Connected (${status.serial.port || 'N/A'})` : 'Disconnected'}\n` +
      `Wireless: ${status.wireless.connected ? 'Connected' : 'Disconnected'}\n` +
      `Last Error: ${status.last_error || 'None'}`
    );
  } catch (err) {
    alert('Device Info:\n\nUnable to fetch runtime status');
  }
});

refresh().catch((err) => {
  console.error('Failed to load settings:', err);
});
