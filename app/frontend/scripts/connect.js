/**
 * connect.js - Connection menu logic.
 */

async function loadSerialPorts() {
  const select = document.getElementById('serialPort');
  select.innerHTML = '<option value="">Select Port</option>';

  try {
    const ports = await window.eyeApi.listSerialPorts();

    const autoOption = document.createElement('option');
    autoOption.value = 'auto';
    autoOption.textContent = 'Auto-detect';
    select.appendChild(autoOption);

    ports.forEach((port) => {
      const option = document.createElement('option');
      option.value = port.device;
      option.textContent = `${port.device} - ${port.description || 'Unknown'}`;
      select.appendChild(option);
    });
  } catch (err) {
    showMessage('Failed to load serial ports', true);
  }
}

function showMessage(message, isError = false) {
  const existing = document.querySelector('.status-message');
  if (existing) existing.remove();

  const msgDiv = document.createElement('div');
  msgDiv.className = `status-message ${isError ? 'error' : 'success'}`;
  msgDiv.textContent = message;

  const form = document.getElementById('connectForm');
  form.parentNode.insertBefore(msgDiv, form);
}

async function resolveSelectedPort(selectedPort) {
  if (selectedPort !== 'auto') {
    return selectedPort;
  }
  const ports = await window.eyeApi.listSerialPorts();
  if (!ports.length) {
    throw new Error('No serial ports found');
  }
  return ports[0].device;
}

document.getElementById('connectForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const networkName = document.getElementById('networkName').value.trim();
  const networkPassword = document.getElementById('networkPassword').value;
  const selectedPort = document.getElementById('serialPort').value;

  if (!networkName || !networkPassword || !selectedPort) {
    showMessage('Please fill in all fields', true);
    return;
  }

  let port;
  try {
    port = await resolveSelectedPort(selectedPort);
  } catch (err) {
    showMessage(err.message, true);
    return;
  }

  sessionStorage.setItem('eye_pending_password', networkPassword);

  const params = new URLSearchParams({
    mode: 'wifi',
    ssid: networkName,
    port,
  });
  window.location.href = `flashing.html?${params.toString()}`;
});

const wiredButton = document.getElementById('wiredConnectBtn');
if (wiredButton) {
  wiredButton.addEventListener('click', async (e) => {
    e.preventDefault();

    const selectedPort = document.getElementById('serialPort').value;
    if (!selectedPort) {
      showMessage('Select a serial port for wired mode', true);
      return;
    }

    let port;
    try {
      port = await resolveSelectedPort(selectedPort);
    } catch (err) {
      showMessage(err.message, true);
      return;
    }

    const params = new URLSearchParams({
      mode: 'wired',
      port,
    });
    window.location.href = `flashing.html?${params.toString()}`;
  });
}

loadSerialPorts();
