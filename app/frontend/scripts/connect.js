/**
 * connect.js - Connection form logic
 */

const API_BASE = 'http://127.0.0.1:5001';

// Load available serial ports on page load
async function loadSerialPorts() {
  try {
    const response = await fetch(`${API_BASE}/serial/ports`);
    const data = await response.json();
    
    if (data.ok && data.data) {
      const select = document.getElementById('serialPort');
      // Clear existing options except first
      select.innerHTML = '<option value="">Select Port</option>';
      
      // Add auto-detect option
      const autoOption = document.createElement('option');
      autoOption.value = 'auto';
      autoOption.textContent = 'Auto-detect';
      select.appendChild(autoOption);
      
      // Add available ports
      data.data.forEach(port => {
        const option = document.createElement('option');
        option.value = port.device;
        option.textContent = `${port.device} - ${port.description}`;
        select.appendChild(option);
      });
    }
  } catch (error) {
    console.error('Failed to load ports:', error);
  }
}

// Show status message
function showMessage(message, isError = false) {
  const existingMsg = document.querySelector('.status-message');
  if (existingMsg) existingMsg.remove();
  
  const msgDiv = document.createElement('div');
  msgDiv.className = `status-message ${isError ? 'error' : 'success'}`;
  msgDiv.textContent = message;
  
  const form = document.getElementById('connectForm');
  form.parentNode.insertBefore(msgDiv, form);
  
  setTimeout(() => msgDiv.remove(), 5000);
}

document.getElementById('connectForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const networkName = document.getElementById('networkName').value;
  const networkPassword = document.getElementById('networkPassword').value;
  let serialPort = document.getElementById('serialPort').value;

  if (!networkName || !networkPassword || !serialPort) {
    showMessage('Please fill in all fields', true);
    return;
  }

  // If auto-detect, get first available port
  if (serialPort === 'auto') {
    try {
      const response = await fetch(`${API_BASE}/serial/ports`);
      const data = await response.json();
      if (data.ok && data.data && data.data.length > 0) {
        serialPort = data.data[0].device;
      } else {
        showMessage('No serial ports found', true);
        return;
      }
    } catch (error) {
      showMessage('Failed to detect port', true);
      return;
    }
  }

  // Store password in sessionStorage (more secure than URL)
  sessionStorage.setItem('wifi_password', networkPassword);

  // Show flashing page immediately
  window.location.href = 'flashing.html?ssid=' + encodeURIComponent(networkName) + 
                         '&port=' + encodeURIComponent(serialPort);
});

// Load ports when page loads
loadSerialPorts();
