/**
 * calibration.js - Calibration flow backed by Flask session state.
 */

let currentNodeIndex = 0;
let calibrationData = [];
let totalNodes = 9;
let sessionId = null;

function getNodePosition(index) {
  const positions = [
    'top-left', 'top-center', 'top-right',
    'middle-left', 'middle-center', 'middle-right',
    'bottom-left', 'bottom-center', 'bottom-right',
  ];
  return positions[index] || `node-${index}`;
}

function updateInstructions() {
  const instructions = document.getElementById('calibrationInstructions');
  const position = getNodePosition(currentNodeIndex);
  instructions.innerHTML = `
    <strong>Active Node:</strong> ${position.replace(/-/g, ' ')}
    (${currentNodeIndex + 1}/${totalNodes})<br>
    <small>Click the highlighted green node to continue</small>
  `;
}

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

async function handleNodeClick(index, nodeElement) {
  if (index !== currentNodeIndex || !sessionId) return;

  nodeElement.classList.remove('active');
  nodeElement.classList.add('completed');

  const event = {
    index,
    position: getNodePosition(index),
    timestamp: Date.now(),
  };
  calibrationData.push(event);

  try {
    await window.eyeApi.submitCalibrationNode({
      session_id: sessionId,
      node_index: index,
      data: event,
    });
  } catch (err) {
    console.error('Failed to submit calibration node:', err);
  }

  if (currentNodeIndex < totalNodes - 1) {
    activateNode(currentNodeIndex + 1);
  } else {
    await completeCalibration();
  }
}

function renderCalibrationNodes() {
  const grid = document.getElementById('calibrationGrid');
  grid.innerHTML = '';

  for (let i = 0; i < totalNodes; i++) {
    const nodeContainer = document.createElement('div');
    nodeContainer.className = 'calibration-node';

    const nodeTarget = document.createElement('div');
    nodeTarget.className = 'node-target inactive';
    nodeTarget.dataset.index = i;
    nodeTarget.dataset.position = getNodePosition(i);
    nodeTarget.addEventListener('click', () => {
      handleNodeClick(i, nodeTarget);
    });

    nodeContainer.appendChild(nodeTarget);
    grid.appendChild(nodeContainer);
  }

  activateNode(0);
}

async function completeCalibration() {
  const instructions = document.getElementById('calibrationInstructions');
  instructions.style.display = 'none';

  const nodes = document.querySelectorAll('.node-target');
  nodes.forEach((node) => {
    node.classList.remove('active', 'inactive');
    node.classList.add('completed');
  });

  try {
    await window.eyeApi.completeCalibrationSession({
      session_id: sessionId,
      calibration_data: calibrationData,
      timestamp: Date.now(),
    });
  } catch (err) {
    console.error('Failed to complete calibration session:', err);
  }

  setTimeout(() => {
    const modal = document.getElementById('completionModal');
    modal.classList.add('active');
  }, 350);
}

function trackMouse(e) {
  const cursor = document.getElementById('userCursor');
  if (!cursor) return;
  if (!document.getElementById('calibrationOverlay').classList.contains('active')) return;

  cursor.style.left = `${e.clientX}px`;
  cursor.style.top = `${e.clientY}px`;
  cursor.style.display = 'block';
}

async function startCalibrationSession() {
  const data = await window.eyeApi.startCalibrationSession({ total_nodes: 9 });
  totalNodes = data.total_nodes || 9;
  sessionId = data.session_id;
  calibrationData = [];
  currentNodeIndex = 0;
  renderCalibrationNodes();
}

document.getElementById('fullscreenBtn').addEventListener('click', async () => {
  const overlay = document.getElementById('calibrationOverlay');
  overlay.classList.add('active');

  try {
    await startCalibrationSession();
  } catch (err) {
    alert(`Failed to start calibration: ${err.message}`);
    return;
  }

  if (document.documentElement.requestFullscreen) {
    document.documentElement.requestFullscreen().catch(() => {});
  }

  document.addEventListener('mousemove', trackMouse);
});

document.getElementById('exitFullscreenBtn').addEventListener('click', () => {
  if (document.exitFullscreen) {
    document.exitFullscreen().catch(() => {});
  }
  window.location.href = 'settings.html';
});

document.getElementById('deviceInfoBtn').addEventListener('click', async () => {
  try {
    const status = await window.eyeApi.getRuntimeState();
    alert(
      `Device Info:\n\n` +
      `Mode: ${status.mode}\n` +
      `Connected: ${status.connected ? 'Yes' : 'No'}\n` +
      `Active Source: ${status.active_source || 'N/A'}\n` +
      `Serial Port: ${status.serial.port || 'N/A'}\n` +
      `Last Error: ${status.last_error || 'None'}`
    );
  } catch (err) {
    alert('Device Info:\n\nUnable to fetch runtime status');
  }
});
