/**
 * calibration.js - Calibration screen logic
 */

const API_BASE = 'http://127.0.0.1:5001';
let currentNodeIndex = 0;
let calibrationData = [];
const totalNodes = 9;

// Generate 9 calibration nodes
function generateCalibrationNodes() {
  const grid = document.getElementById('calibrationGrid');
  grid.innerHTML = '';
  
  for (let i = 0; i < totalNodes; i++) {
    const nodeContainer = document.createElement('div');
    nodeContainer.className = 'calibration-node';
    
    const nodeTarget = document.createElement('div');
    nodeTarget.className = 'node-target inactive';
    nodeTarget.dataset.index = i;
    nodeTarget.dataset.position = getNodePosition(i);
    
    nodeTarget.addEventListener('click', () => handleNodeClick(i, nodeTarget));
    
    nodeContainer.appendChild(nodeTarget);
    grid.appendChild(nodeContainer);
  }
  
  // Activate first node
  activateNode(0);
}

// Get node position description
function getNodePosition(index) {
  const positions = [
    'top-left', 'top-center', 'top-right',
    'middle-left', 'middle-center', 'middle-right',
    'bottom-left', 'bottom-center', 'bottom-right'
  ];
  return positions[index];
}

// Activate a specific node
function activateNode(index) {
  const nodes = document.querySelectorAll('.node-target');
  nodes.forEach((node, i) => {
    if (i === index) {
      node.classList.remove('inactive');
      node.classList.add('active');
    } else if (!node.classList.contains('completed')) {
      node.classList.add('inactive');
      node.classList.remove('active');
    }
  });
  
  currentNodeIndex = index;
  updateInstructions();
}

// Update instruction text
function updateInstructions() {
  const instructions = document.getElementById('calibrationInstructions');
  const position = getNodePosition(currentNodeIndex);
  instructions.innerHTML = `
    <strong>Active Node:</strong> ${position.replace(/-/g, ' ')} 
    (${currentNodeIndex + 1}/${totalNodes})<br>
    <small>Click the highlighted green node to continue</small>
  `;
}

// Handle node click
function handleNodeClick(index, nodeElement) {
  if (index !== currentNodeIndex) return;
  
  // Mark as completed
  nodeElement.classList.remove('active');
  nodeElement.classList.add('completed');
  
  // Store calibration data
  calibrationData.push({
    index: index,
    position: getNodePosition(index),
    timestamp: Date.now()
  });
  
  // Move to next node or complete
  if (currentNodeIndex < totalNodes - 1) {
    activateNode(currentNodeIndex + 1);
  } else {
    completeCalibration();
  }
}

// Complete calibration
function completeCalibration() {
  const instructions = document.getElementById('calibrationInstructions');
  instructions.style.display = 'none';
  
  // Show all nodes as completed
  const nodes = document.querySelectorAll('.node-target');
  nodes.forEach(node => {
    node.classList.remove('active', 'inactive');
    node.classList.add('completed');
  });
  
  // Show completion modal
  setTimeout(() => {
    const modal = document.getElementById('completionModal');
    modal.classList.add('active');
  }, 500);
  
  // Save calibration data to backend
  saveCalibrationData();
}

// Save calibration data
async function saveCalibrationData() {
  try {
    const response = await fetch(`${API_BASE}/prefs/calibration`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        calibration_data: calibrationData,
        timestamp: Date.now()
      })
    });
    
    const data = await response.json();
    if (data.ok) {
      console.log('Calibration saved successfully', data.data);
    }
  } catch (error) {
    console.error('Failed to save calibration:', error);
  }
}

// Track mouse for user cursor display
function trackMouse(e) {
  const cursor = document.getElementById('userCursor');
  if (cursor && document.getElementById('calibrationOverlay').classList.contains('active')) {
    cursor.style.left = e.clientX + 'px';
    cursor.style.top = e.clientY + 'px';
    cursor.style.display = 'block';
  }
}

// Enter fullscreen and start calibration
document.getElementById('fullscreenBtn').addEventListener('click', () => {
  const overlay = document.getElementById('calibrationOverlay');
  overlay.classList.add('active');
  
  // Generate nodes
  generateCalibrationNodes();
  
  // Try to enter fullscreen
  if (document.documentElement.requestFullscreen) {
    document.documentElement.requestFullscreen().catch(err => {
      console.log('Fullscreen not supported:', err);
    });
  }
  
  // Track mouse
  document.addEventListener('mousemove', trackMouse);
});

// Exit fullscreen and go to settings
document.getElementById('exitFullscreenBtn').addEventListener('click', () => {
  // Exit fullscreen
  if (document.exitFullscreen) {
    document.exitFullscreen().catch(err => console.log(err));
  }
  
  // Navigate to settings
  window.location.href = 'settings.html';
});

// Show device info
document.getElementById('deviceInfoBtn').addEventListener('click', async () => {
  try {
    const response = await fetch(`${API_BASE}/serial/status`);
    const data = await response.json();
    
    if (data.ok) {
      const status = data.data;
      alert(
        `Device Info:\n\n` +
        `Status: ${status.connected ? 'Connected' : 'Disconnected'}\n` +
        `Port: ${status.port || 'N/A'}\n` +
        `Error: ${status.last_error || 'None'}`
      );
    }
  } catch (error) {
    alert('Device Info:\n\nStatus: Unable to fetch\nError: Backend not responding');
  }
});
