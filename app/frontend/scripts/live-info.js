/**
 * live-info.js - Live Info View logic
 * Shows real-time connection status and monitoring for ESP32 camera device
 */

const API_BASE = 'http://127.0.0.1:5001';
const terminal = document.getElementById('terminal');
const statusElement = document.getElementById('connectionStatus');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const wifiInfoElement = document.getElementById('wifiInfo');
const serialInfoElement = document.getElementById('serialInfo');
const cameraInfoElement = document.getElementById('cameraInfo');

let pollInterval = null;
let lastStatus = null;
let isDestroyed = false;

// Add log entry to terminal (with memory management)
function addLog(message, type = 'info') {
  if (isDestroyed) return;
  
  const line = document.createElement('div');
  line.className = 'terminal-line';
  
  const timestamp = new Date().toLocaleTimeString('en-US', { hour12: false });
  const timestampSpan = document.createElement('span');
  timestampSpan.className = 'terminal-timestamp';
  timestampSpan.textContent = `[${timestamp}] `;
  
  const messageSpan = document.createElement('span');
  messageSpan.className = `terminal-${type}`;
  messageSpan.textContent = message;
  
  line.appendChild(timestampSpan);
  line.appendChild(messageSpan);
  terminal.appendChild(line);
  
  // Limit terminal lines to prevent memory issues
  const maxLines = 100;
  while (terminal.children.length > maxLines) {
    terminal.removeChild(terminal.firstChild);
  }
  
  // Auto-scroll to bottom
  terminal.scrollTop = terminal.scrollHeight;
}

// Update connection status badge
function updateStatus(status, message) {
  if (isDestroyed) return;
  
  statusElement.className = `connection-status ${status}`;
  statusDot.className = `status-dot ${status}`;
  statusText.textContent = message || 'Unknown status';
}

// Update info panel with real connection details
function updateInfoPanel(data) {
  if (isDestroyed) return;
  
  try {
    // WiFi info
    const wifiStatus = data.wifi_connected ? 'Connected' : 'Not Connected';
    const wifiSSID = data.wifi_ssid || 'N/A';
    const wifiIP = data.wifi_ip || 'N/A';
    wifiInfoElement.innerHTML = `<strong>WiFi:</strong> ${wifiStatus}${data.wifi_connected ? ` | SSID: ${wifiSSID} | IP: ${wifiIP}` : ''}`;
    
    // Serial info
    const serialStatus = data.connected ? 'Connected' : 'Disconnected';
    const serialPort = data.port || 'N/A';
    const baudRate = data.baud_rate || 115200;
    serialInfoElement.innerHTML = `<strong>Serial:</strong> ${serialStatus}${data.connected ? ` | Port: ${serialPort} | Baud: ${baudRate}` : ''}`;
    
    // Camera info (if available from device)
    const cameraStatus = data.camera_ready ? 'Ready' : 'Not Available';
    const frameSize = data.frame_size || 'QVGA';
    const quality = data.jpeg_quality || 'Unknown';
    cameraInfoElement.innerHTML = `<strong>Camera:</strong> ${cameraStatus}${data.camera_ready ? ` | Size: ${frameSize} | Quality: ${quality}` : ''}`;
  } catch (error) {
    console.error('Error updating info panel:', error);
  }
}

// Check backend and device status
async function checkConnectionStatus() {
  if (isDestroyed) return;
  
  try {
    // Check if backend is reachable
    const response = await fetch(`${API_BASE}/serial/status`, {
      signal: AbortSignal.timeout(3000) // 3 second timeout
    });
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    
    const data = await response.json();
    
    if (data.ok) {
      const status = data.data;
      
      // Determine overall connection state
      if (status.connected) {
        // ESP32 is connected via serial
        updateStatus('connected', 'ESP32 Connected via Serial');
        updateInfoPanel(status);
        
        // Log only state changes
        if (lastStatus !== 'connected') {
          addLog(`ESP32 device connected on ${status.port}`, 'success');
          if (status.wifi_connected) {
            addLog(`WiFi connected: ${status.wifi_ssid} (${status.wifi_ip})`, 'success');
          }
          addLog('Camera server ready for streaming', 'info');
        }
        
        lastStatus = 'connected';
      } else {
        // No serial connection
        updateStatus('disconnected', 'No Device Connected');
        updateInfoPanel(status);
        
        if (lastStatus !== 'disconnected') {
          addLog('No ESP32 device detected', 'warning');
          addLog('Waiting for device connection...', 'info');
          if (status.last_error) {
            addLog(`Last error: ${status.last_error}`, 'error');
          }
        }
        
        lastStatus = 'disconnected';
      }
    }
  } catch (error) {
    if (isDestroyed) return;
    
    updateStatus('error', 'Backend Connection Error');
    wifiInfoElement.innerHTML = '<strong>WiFi:</strong> Unable to fetch';
    serialInfoElement.innerHTML = '<strong>Serial:</strong> Unable to fetch';
    cameraInfoElement.innerHTML = '<strong>Camera:</strong> Unable to fetch';
    
    if (lastStatus !== 'error') {
      addLog('Cannot connect to backend server', 'error');
      addLog(`Error: ${error.message}`, 'error');
      addLog('Make sure run_server.py is running on port 5001', 'warning');
    }
    
    lastStatus = 'error';
  }
}

// Start polling for status updates
function startPolling() {
  addLog('Live monitoring started', 'success');
  addLog('Polling device status every 2 seconds...', 'info');
  
  // Initial check
  checkConnectionStatus();
  
  // Poll every 2 seconds
  pollInterval = setInterval(checkConnectionStatus, 2000);
}

// Stop polling and cleanup
function stopPolling() {
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }
  isDestroyed = true;
}

// Main initialization
function initialize() {
  addLog('EyeCue Live Info View initialized', 'info');
  addLog('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'info');
  addLog('ESP32 Camera Server Connection Monitor', 'info');
  addLog('This page shows real-time connection status', 'info');
  addLog('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━', 'info');
  
  updateStatus('searching', 'Checking backend connection...');
  
  // Start status polling
  startPolling();
}

// Back button
document.getElementById('backBtn').addEventListener('click', () => {
  stopPolling();
  window.location.href = 'settings.html';
});

// Device Info modal
document.getElementById('deviceInfoBtn').addEventListener('click', async () => {
  try {
    const response = await fetch(`${API_BASE}/serial/status`);
    const data = await response.json();
    
    if (data.ok) {
      const status = data.data;
      const connectionMode = localStorage.getItem('connectionMode') || 'wifi';
      
      alert(
        `Device Info:\n\n` +
        `Connection Mode: ${connectionMode.toUpperCase()}\n` +
        `Serial Status: ${status.connected ? 'Connected' : 'Disconnected'}\n` +
        `Port: ${status.port || 'N/A'}\n` +
        `Baud Rate: ${status.baud_rate || 'N/A'}\n` +
        `WiFi: ${status.wifi_connected ? 'Connected' : 'N/A'}\n` +
        `SSID: ${status.wifi_ssid || 'N/A'}\n` +
        `IP: ${status.wifi_ip || 'N/A'}\n` +
        `Camera: ${status.camera_ready ? 'Ready' : 'N/A'}\n` +
        `Last Error: ${status.last_error || 'None'}`
      );
    }
  } catch (error) {
    alert(
      `Device Info:\n\n` +
      `Unable to fetch device information.\n` +
      `Make sure backend is running.`
    );
  }
});

// Cleanup on page unload
window.addEventListener('beforeunload', stopPolling);

// Initialize on page load
initialize();
