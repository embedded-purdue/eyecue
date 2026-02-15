/**
 * settings.js - Settings page logic
 */

const API_BASE = 'http://127.0.0.1:5001';

// Load settings from backend or localStorage
async function loadSettings() {
  try {
    const response = await fetch(`${API_BASE}/prefs`);
    const data = await response.json();
    
    if (data.ok && data.data) {
      const prefs = data.data;
      const settings = {
        connectionMode: prefs.connection_method || localStorage.getItem('connectionMode') || 'wifi',
        horizontalSensitivity: prefs.horizontal_sensitivity || parseInt(localStorage.getItem('horizontalSensitivity')) || 50,
        verticalSensitivity: prefs.vertical_sensitivity || parseInt(localStorage.getItem('verticalSensitivity')) || 50
      };
      
      applySettings(settings);
      return settings;
    }
  } catch (error) {
    console.error('Failed to load settings from backend:', error);
  }
  
  // Fallback to localStorage
  const settings = {
    connectionMode: localStorage.getItem('connectionMode') || 'wifi',
    horizontalSensitivity: parseInt(localStorage.getItem('horizontalSensitivity')) || 50,
    verticalSensitivity: parseInt(localStorage.getItem('verticalSensitivity')) || 50
  };
  
  applySettings(settings);
  return settings;
}

// Apply settings to UI
function applySettings(settings) {
  // Apply connection mode
  document.querySelectorAll('.mode-option').forEach(option => {
    option.classList.toggle('active', option.dataset.mode === settings.connectionMode);
  });
  
  // Apply sensitivity values
  document.getElementById('horizontalSensitivity').value = settings.horizontalSensitivity;
  document.getElementById('verticalSensitivity').value = settings.verticalSensitivity;
  document.getElementById('horizontalValue').textContent = settings.horizontalSensitivity;
  document.getElementById('verticalValue').textContent = settings.verticalSensitivity;
}

// Save settings to backend and localStorage
async function saveSettings() {
  const connectionMode = document.querySelector('.mode-option.active').dataset.mode;
  const horizontalSensitivity = parseInt(document.getElementById('horizontalSensitivity').value);
  const verticalSensitivity = parseInt(document.getElementById('verticalSensitivity').value);
  
  // Save to localStorage
  localStorage.setItem('connectionMode', connectionMode);
  localStorage.setItem('horizontalSensitivity', horizontalSensitivity);
  localStorage.setItem('verticalSensitivity', verticalSensitivity);
  
  // Save to backend
  try {
    await fetch(`${API_BASE}/prefs`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        connection_method: connectionMode,
        horizontal_sensitivity: horizontalSensitivity,
        vertical_sensitivity: verticalSensitivity
      })
    });
  } catch (error) {
    console.error('Failed to save settings to backend:', error);
  }
}

// Connection mode selection
document.getElementById('wifiMode').addEventListener('click', function() {
  document.querySelectorAll('.mode-option').forEach(opt => opt.classList.remove('active'));
  this.classList.add('active');
  saveSettings();
});

document.getElementById('wiredMode').addEventListener('click', function() {
  document.querySelectorAll('.mode-option').forEach(opt => opt.classList.remove('active'));
  this.classList.add('active');
  saveSettings();
});

// Horizontal sensitivity slider
document.getElementById('horizontalSensitivity').addEventListener('input', function() {
  document.getElementById('horizontalValue').textContent = this.value;
  saveSettings();
});

// Vertical sensitivity slider
document.getElementById('verticalSensitivity').addEventListener('input', function() {
  document.getElementById('verticalValue').textContent = this.value;
  saveSettings();
});

// Recalibrate button
document.getElementById('recalibrateBtn').addEventListener('click', () => {
  window.location.href = 'calibration.html';
});

// Advanced Settings button
document.getElementById('advancedSettingsBtn').addEventListener('click', () => {
  window.location.href = 'advanced-settings.html';
});

// Live Info View button
document.getElementById('liveInfoBtn').addEventListener('click', () => {
  window.location.href = 'live-info.html';
});

// Flash WiFi Information button
document.getElementById('flashWifiBtn').addEventListener('click', () => {
  window.location.href = 'connect.html';
});

// Device Info button
document.getElementById('deviceInfoBtn').addEventListener('click', async () => {
  try {
    const response = await fetch(`${API_BASE}/serial/status`);
    const data = await response.json();
    
    if (data.ok) {
      const status = data.data;
      const connectionMode = localStorage.getItem('connectionMode') || 'wifi';
      
      alert(
        `Device Info:\n\n` +
        `Connection: ${connectionMode.toUpperCase()}\n` +
        `Status: ${status.connected ? 'Connected' : 'Disconnected'}\n` +
        `Port: ${status.port || 'N/A'}\n` +
        `Error: ${status.last_error || 'None'}`
      );
    }
  } catch (error) {
    alert('Device Info:\n\nUnable to fetch device information');
  }
});

// Load settings on page load
loadSettings();
