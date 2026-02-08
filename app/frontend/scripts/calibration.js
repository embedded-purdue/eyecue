/**
 * calibration.js - Calibration screen logic
 */

// Enter fullscreen on button click
document.getElementById('fullscreenBtn').addEventListener('click', () => {
  if (document.documentElement.requestFullscreen) {
    document.documentElement.requestFullscreen();
  }
  // TODO: Start calibration process
});

// Show device info
document.getElementById('deviceInfoBtn').addEventListener('click', () => {
  alert('Device Info:\n\nStatus: Connected\nFirmware: v1.0.0\nSerial: ESP32-001');
  // TODO: Show proper device info modal
});
