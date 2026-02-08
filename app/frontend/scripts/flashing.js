/**
 * flashing.js - Progress screen logic
 */

// Simulate flashing progress and navigate to calibration after completion
setTimeout(() => {
  window.location.href = 'calibration.html';
}, 3500); // Match the animation duration
