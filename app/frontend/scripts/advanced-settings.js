/**
 * advanced-settings.js - Advanced Settings page logic
 */

const API_BASE = 'http://127.0.0.1:5001';

// Load advanced settings from backend or localStorage
async function loadAdvancedSettings() {
  try {
    const response = await fetch(`${API_BASE}/prefs`);
    const data = await response.json();
    
    if (data.ok && data.data) {
      const prefs = data.data;
      const settings = {
        preference1: prefs.preference_1 || localStorage.getItem('preference1') || 'default',
        preference2: prefs.preference_2 || localStorage.getItem('preference2') || 'default',
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
    preference1: localStorage.getItem('preference1') || 'default',
    preference2: localStorage.getItem('preference2') || 'default',
    horizontalSensitivity: parseInt(localStorage.getItem('horizontalSensitivity')) || 50,
    verticalSensitivity: parseInt(localStorage.getItem('verticalSensitivity')) || 50
  };
  
  applySettings(settings);
  return settings;
}

// Apply settings to UI
function applySettings(settings) {
  // Apply preference values
  document.getElementById('preference1').value = settings.preference1;
  document.getElementById('preference2').value = settings.preference2;
  
  // Apply sensitivity values
  document.getElementById('horizontalSensitivity').value = settings.horizontalSensitivity;
  document.getElementById('verticalSensitivity').value = settings.verticalSensitivity;
  document.getElementById('horizontalValue').textContent = settings.horizontalSensitivity;
  document.getElementById('verticalValue').textContent = settings.verticalSensitivity;
}

// Save settings to backend and localStorage
async function saveSettings() {
  const preference1 = document.getElementById('preference1').value;
  const preference2 = document.getElementById('preference2').value;
  const horizontalSensitivity = parseInt(document.getElementById('horizontalSensitivity').value);
  const verticalSensitivity = parseInt(document.getElementById('verticalSensitivity').value);
  
  // Save to localStorage
  localStorage.setItem('preference1', preference1);
  localStorage.setItem('preference2', preference2);
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
        preference_1: preference1,
        preference_2: preference2,
        horizontal_sensitivity: horizontalSensitivity,
        vertical_sensitivity: verticalSensitivity
      })
    });
  } catch (error) {
    console.error('Failed to save settings to backend:', error);
  }
}

// Preference dropdowns
document.getElementById('preference1').addEventListener('change', saveSettings);
document.getElementById('preference2').addEventListener('change', saveSettings);

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

// Back button
document.getElementById('backBtn').addEventListener('click', () => {
  window.location.href = 'settings.html';
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
loadAdvancedSettings();
