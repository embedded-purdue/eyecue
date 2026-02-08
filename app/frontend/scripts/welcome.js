/**
 * welcome.js - Welcome screen logic
 */

// Auto-navigate to connect page after 2 seconds
setTimeout(() => {
  window.location.href = 'connect.html';
}, 2000);

// Or immediately on click
document.body.addEventListener('click', () => {
  window.location.href = 'connect.html';
});
