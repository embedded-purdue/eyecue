/**
 * live-info.js - Live Info View logic
 */

const API_BASE = 'http://127.0.0.1:5001';
const terminal = document.getElementById('terminal');
const statusElement = document.getElementById('connectionStatus');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

let logCount = 0;
let connectionAttempts = 0;
const maxAttempts = 3;

// Add log entry to terminal
function addLog(message, type = 'info') {
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
  
  // Auto-scroll to bottom
  terminal.scrollTop = terminal.scrollHeight;
  
  logCount++;
}

// Update connection status
function updateStatus(status) {
  statusElement.className = `connection-status ${status}`;
  statusDot.className = `status-dot ${status}`;
  
  const messages = {
    searching: 'Searching for ESP32 device...',
    connected: 'Connected to ESP32',
    disconnected: 'No device found - Proceeding in offline mode'
  };
  
  statusText.textContent = messages[status] || messages.disconnected;
}

// Check if Web Bluetooth is available
async function checkBluetoothSupport() {
  if (!navigator.bluetooth) {
    addLog('Web Bluetooth API not available in this environment', 'warning');
    addLog('Tip: Bluetooth requires HTTPS or localhost', 'info');
    return false;
  }
  
  addLog('Web Bluetooth API detected', 'success');
  return true;
}

// Try to connect to ESP32 via Bluetooth
async function attemptBluetoothConnection() {
  try {
    addLog('Requesting Bluetooth device...', 'info');
    
    // Request device with ESP32 service UUID (optional - can be more specific)
    const device = await navigator.bluetooth.requestDevice({
      acceptAllDevices: true,
      optionalServices: ['battery_service', 'generic_access']
    });
    
    addLog(`Found device: ${device.name || 'Unknown'}`, 'success');
    addLog(`Device ID: ${device.id}`, 'info');
    
    // Try to connect to GATT server
    addLog('Connecting to GATT server...', 'info');
    const server = await device.gatt.connect();
    
    addLog('Connected to GATT server!', 'success');
    updateStatus('connected');
    
    // Simulate some data packets
    simulateDataFlow(true);
    
    return true;
  } catch (error) {
    if (error.name === 'NotFoundError') {
      addLog('No device selected by user', 'warning');
    } else {
      addLog(`Connection error: ${error.message}`, 'error');
    }
    return false;
  }
}

// Check WiFi/Serial connection status from backend
async function checkBackendConnection() {
  try {
    addLog('Checking backend serial connection...', 'info');
    const response = await fetch(`${API_BASE}/serial/status`);
    const data = await response.json();
    
    if (data.ok && data.data.connected) {
      addLog(`Serial connection active on ${data.data.port}`, 'success');
      updateStatus('connected');
      simulateDataFlow(true);
      return true;
    } else {
      addLog('No active serial connection', 'warning');
      return false;
    }
  } catch (error) {
    addLog('Backend not responding', 'warning');
    return false;
  }
}

// Simulate data flow for demonstration
function simulateDataFlow(isConnected) {
  if (!isConnected) {
    addLog('No active connection - running in offline mode', 'warning');
    addLog('App functionality continues normally', 'info');
    updateStatus('disconnected');
    return;
  }
  
  // Simulate some data packets
  const packets = [
    { type: 'info', msg: 'Client [GET] /info | packets 2026-02-15T19:00:15Z [10s] - 10 dropped | 2% drop | 10ms ping' },
    { type: 'info', msg: 'Client [GET] /info | packets 2026-02-15T19:00:25Z [10s] - 0 dropped | 0% drop | 9ms ping' },
    { type: 'success', msg: 'Eye tracking data streaming...' },
    { type: 'info', msg: 'Cursor position: (1024, 768)' },
    { type: 'info', msg: 'Gaze angle: (15.3°, -8.2°)' }
  ];
  
  let index = 0;
  const interval = setInterval(() => {
    if (index < packets.length) {
      addLog(packets[index].msg, packets[index].type);
      index++;
    } else {
      clearInterval(interval);
      addLog('Live data feed active', 'success');
    }
  }, 800);
}

// Main initialization
async function initialize() {
  addLog('EyeCue Live Info View initialized', 'success');
  
  // First check backend connection (WiFi/Serial)
  const backendConnected = await checkBackendConnection();
  
  if (backendConnected) {
    // Already connected via serial, no need for Bluetooth
    return;
  }
  
  // Check Bluetooth support
  const hasBluetoothSupport = await checkBluetoothSupport();
  
  if (!hasBluetoothSupport) {
    addLog('Continuing without Bluetooth connection', 'warning');
    updateStatus('disconnected');
    simulateDataFlow(false);
    return;
  }
  
  // Note: We don't automatically request Bluetooth to avoid popup spam
  // User can manually trigger it if needed
  addLog('Click "Connect Bluetooth" to manually connect a device', 'info');
  updateStatus('disconnected');
  simulateDataFlow(false);
}

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

// Initialize on page load
initialize();
