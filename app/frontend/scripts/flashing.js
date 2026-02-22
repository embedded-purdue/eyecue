/**
 * flashing.js - Starts runtime and transitions to next screen.
 */

const urlParams = new URLSearchParams(window.location.search);

function updateText(message) {
  const el = document.querySelector('.progress-text');
  if (el) el.textContent = message;
}

async function startRuntime() {
  const mode = (urlParams.get('mode') || 'serial').toLowerCase();
  const ssid = urlParams.get('ssid') || '';
  const port = urlParams.get('port') || '';
  const password = sessionStorage.getItem('eye_pending_password') || '';

  if (!port) {
    updateText('Missing serial port. Returning to connection menu...');
    setTimeout(() => {
      window.location.href = 'connect.html';
    }, 1500);
    return;
  }

  try {
    updateText('Starting runtime agents...');

    await window.eyeApi.startRuntime({
      mode,
      ssid,
      password,
      port,
      baud: 115200,
    });

    const bootstrap = await window.eyeApi.bootstrap();
    sessionStorage.removeItem('eye_pending_password');

    if (bootstrap.has_onboarded) {
      window.location.href = 'settings.html';
      return;
    }

    window.location.href = 'calibration.html';
  } catch (err) {
    updateText(`Connection failed: ${err.message}`);
    setTimeout(() => {
      window.location.href = 'connect.html';
    }, 1800);
  }
}

startRuntime();
