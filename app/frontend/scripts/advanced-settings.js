/**
 * advanced-settings.js - Advanced preferences page backed by Flask.
 */

let prefsState = null;

function applySettings(prefs) {
  document.getElementById('preference1').value = prefs.preference_1 || 'default';
  document.getElementById('preference2').value = prefs.preference_2 || 'default';

  const horizontal = Number(prefs.horizontal_sensitivity || 50);
  const vertical = Number(prefs.vertical_sensitivity || 50);

  document.getElementById('horizontalSensitivity').value = horizontal;
  document.getElementById('verticalSensitivity').value = vertical;
  document.getElementById('horizontalValue').textContent = String(horizontal);
  document.getElementById('verticalValue').textContent = String(vertical);
}

async function refresh() {
  prefsState = await window.eyeApi.getPrefs();
  applySettings(prefsState);
}

async function saveSettings() {
  if (!prefsState) return;

  prefsState = await window.eyeApi.updatePrefs({
    preference_1: document.getElementById('preference1').value,
    preference_2: document.getElementById('preference2').value,
    horizontal_sensitivity: Number(document.getElementById('horizontalSensitivity').value),
    vertical_sensitivity: Number(document.getElementById('verticalSensitivity').value),
  });
}

document.getElementById('preference1').addEventListener('change', saveSettings);
document.getElementById('preference2').addEventListener('change', saveSettings);

document.getElementById('horizontalSensitivity').addEventListener('input', function onHorizontalInput() {
  document.getElementById('horizontalValue').textContent = this.value;
  saveSettings();
});

document.getElementById('verticalSensitivity').addEventListener('input', function onVerticalInput() {
  document.getElementById('verticalValue').textContent = this.value;
  saveSettings();
});

document.getElementById('backBtn').addEventListener('click', () => {
  window.location.href = 'settings.html';
});

document.getElementById('deviceInfoBtn').addEventListener('click', async () => {
  try {
    const status = await window.eyeApi.getRuntimeState();
    alert(
      `Device Info:\n\n` +
      `Mode: ${status.mode}\n` +
      `Connected: ${status.connected ? 'Yes' : 'No'}\n` +
      `Active Source: ${status.active_source || 'N/A'}\n` +
      `Serial Port: ${status.serial.port || 'N/A'}\n` +
      `Last Error: ${status.last_error || 'None'}`
    );
  } catch (err) {
    alert('Device Info:\n\nUnable to fetch runtime status');
  }
});

refresh().catch((err) => {
  console.error('Failed to load advanced settings:', err);
});
