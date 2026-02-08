/**
 * connect.js - Connection form logic
 */

document.getElementById('connectForm').addEventListener('submit', async (e) => {
  e.preventDefault();

  const networkName = document.getElementById('networkName').value;
  const networkPassword = document.getElementById('networkPassword').value;
  const serialPort = document.getElementById('serialPort').value;

  // Navigate to flashing page
  window.location.href = 'flashing.html';

  // TODO: Send credentials to backend
  // const response = await fetch('/serial/connect', {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  //   body: new URLSearchParams({ ssid: networkName, password: networkPassword })
  // });
});
