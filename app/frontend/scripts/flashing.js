/**
 * flashing.js - Progress screen logic
 */

const API_BASE = 'http://127.0.0.1:5001';

// Get credentials from URL parameters
const urlParams = new URLSearchParams(window.location.search);
const ssid = urlParams.get('ssid');
const port = urlParams.get('port');
const password = sessionStorage.getItem('wifi_password');

async function connectToDevice() {
  try {
    const response = await fetch(`${API_BASE}/serial/connect`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        port: port,
        ssid: ssid,
        password: password || '',
        baud: 115200
      })
    });

    const data = await response.json();
    
    if (data.ok) {
      // Success! Navigate to calibration after a short delay
      setTimeout(() => {
        window.location.href = 'calibration.html';
      }, 1500);
    } else {
      // Connection failed
      alert('Connection failed: ' + (data.error || 'Unknown error'));
      window.location.href = 'connect.html';
    }
  } catch (error) {
    console.error('Connection error:', error);
    // Still proceed to calibration even if backend fails (for demo purposes)
    setTimeout(() => {
      window.location.href = 'calibration.html';
    }, 3500);
  }
}

// Store password from previous page (if passed via form)
if (ssid && port) {
  // Start connection process
  connectToDevice();
} else {
  // Auto-navigate after animation completes
  setTimeout(() => {
    window.location.href = 'calibration.html';
  }, 3500);
}
