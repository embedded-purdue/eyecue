/**
 * calibrate.js — 5-point calibration flow + quick recalibrate
 *
 * Reads the URL query param ?mode=full|quick to decide which flow to run.
 * Communicates with the backend via the same api-client.js used elsewhere.
 */

// 3x3 grid — must match CALIBRATION_POINTS in app/services/calibration.py
const CALIBRATION_POINTS = [
  { x: 0.08, y: 0.08, label: "Top-Left" },
  { x: 0.50, y: 0.08, label: "Top-Center" },
  { x: 0.92, y: 0.08, label: "Top-Right" },
  { x: 0.08, y: 0.50, label: "Middle-Left" },
  { x: 0.50, y: 0.50, label: "Center" },
  { x: 0.92, y: 0.50, label: "Middle-Right" },
  { x: 0.08, y: 0.92, label: "Bottom-Left" },
  { x: 0.50, y: 0.92, label: "Bottom-Center" },
  { x: 0.92, y: 0.92, label: "Bottom-Right" },
];

const dot = document.getElementById("targetDot");
const instructionPanel = document.getElementById("instructionPanel");
const instructionTitle = document.getElementById("instructionTitle");
const instructionText = document.getElementById("instructionText");
const progressDotsEl = document.getElementById("progressDots");
const statusText = document.getElementById("statusText");
const gazeStatus = document.getElementById("gazeStatus");
const quickPanel = document.getElementById("quickPanel");
const donePanel = document.getElementById("donePanel");
const countdownEl = document.getElementById("countdown");

let currentPoint = 0;
let mode = "full"; // "full" or "quick"
let gazePoller = null;
let recording = false;
let readyToCapture = false;

function getScreenSize() {
  return { w: window.screen.width, h: window.screen.height };
}

function positionDot(xPct, yPct) {
  const screen = getScreenSize();
  dot.style.left = `${xPct * screen.w}px`;
  dot.style.top = `${yPct * screen.h}px`;
  dot.classList.remove("captured");
}

function buildProgressDots() {
  progressDotsEl.innerHTML = "";
  for (let i = 0; i < CALIBRATION_POINTS.length; i++) {
    const d = document.createElement("div");
    d.className = "progress-dot";
    d.dataset.index = i;
    progressDotsEl.appendChild(d);
  }
}

function updateProgressDots() {
  const dots = progressDotsEl.querySelectorAll(".progress-dot");
  dots.forEach((d, i) => {
    d.classList.toggle("done", i < currentPoint);
    d.classList.toggle("active", i === currentPoint);
  });
}

async function pollGaze() {
  try {
    const data = await window.eyeApi.request("/runtime/gaze/current");
    if (data && data.available) {
      gazeStatus.classList.add("tracking");
      statusText.textContent = `Gaze: H=${data.angle_h.toFixed(1)}° V=${data.angle_v.toFixed(1)}°`;
    } else {
      gazeStatus.classList.remove("tracking");
      statusText.textContent = "Waiting for gaze detection...";
    }
  } catch {
    gazeStatus.classList.remove("tracking");
    statusText.textContent = "Backend not reachable";
  }
}

async function startFullCalibration() {
  try {
    await window.eyeApi.request("/runtime/calibrate/start", { method: "POST", body: {} });
  } catch (err) {
    statusText.textContent = `Error: ${err.message}`;
    return;
  }

  buildProgressDots();
  currentPoint = 0;
  showPoint(0);
}

function showPoint(index) {
  if (index >= CALIBRATION_POINTS.length) {
    finishCalibration();
    return;
  }
  currentPoint = index;
  readyToCapture = false;
  recording = false;
  const pt = CALIBRATION_POINTS[index];
  positionDot(pt.x, pt.y);
  updateProgressDots();
  instructionTitle.textContent = `Point ${index + 1} of ${CALIBRATION_POINTS.length} — ${pt.label}`;
  instructionText.innerHTML = 'Hold steady — look at the dot...';

  // wait briefly for the pupil buffer to fill with stable readings
  setTimeout(() => {
    readyToCapture = true;
    instructionText.innerHTML = 'Now press <kbd>Space</kbd> to capture';
  }, 700);
}

async function recordCurrentPoint() {
  if (recording || !readyToCapture) return;
  recording = true;

  const screen = getScreenSize();
  const pt = CALIBRATION_POINTS[currentPoint];
  const screenX = pt.x * screen.w;
  const screenY = pt.y * screen.h;

  try {
    await window.eyeApi.request("/runtime/calibrate/record", {
      method: "POST",
      body: {
        point_index: currentPoint,
        screen_x: screenX,
        screen_y: screenY,
      },
    });

    dot.classList.add("captured");
    updateProgressDots();

    // brief pause then move to next
    setTimeout(() => {
      showPoint(currentPoint + 1);
    }, 500);
  } catch (err) {
    statusText.textContent = `Record failed: ${err.message}`;
    recording = false;
  }
}

async function finishCalibration() {
  try {
    await window.eyeApi.request("/runtime/calibrate/finish", { method: "POST", body: {} });
    showDone();
  } catch (err) {
    statusText.textContent = `Finish failed: ${err.message}`;
  }
}

async function startQuickRecalibrate() {
  quickPanel.classList.remove("hidden");
  instructionPanel.classList.add("hidden");

  const screen = getScreenSize();
  positionDot(0.5, 0.5);
  recording = false;
}

async function recordQuickRecalibrate() {
  if (recording) return;
  recording = true;

  const screen = getScreenSize();
  try {
    await window.eyeApi.request("/runtime/calibrate/quick", {
      method: "POST",
      body: {
        screen_x: screen.w * 0.5,
        screen_y: screen.h * 0.5,
      },
    });
    dot.classList.add("captured");
    showDone();
  } catch (err) {
    statusText.textContent = `Quick recalibrate failed: ${err.message}`;
    recording = false;
  }
}

function showDone() {
  donePanel.classList.remove("hidden");
  let count = 3;
  countdownEl.textContent = count;
  const timer = setInterval(() => {
    count -= 1;
    countdownEl.textContent = count;
    if (count <= 0) {
      clearInterval(timer);
      window.close();
    }
  }, 1000);
}

function handleKeydown(event) {
  if (event.key === " " || event.key === "Enter") {
    event.preventDefault();
    if (mode === "quick") {
      recordQuickRecalibrate();
    } else {
      recordCurrentPoint();
    }
  }
  if (event.key === "Escape") {
    cancelAndClose();
  }
}

async function cancelAndClose() {
  try {
    await window.eyeApi.request("/runtime/calibrate/cancel", { method: "POST", body: {} });
  } catch {
    // best-effort
  }
  window.close();
}

async function init() {
  const params = new URLSearchParams(window.location.search);
  mode = params.get("mode") || "full";

  document.addEventListener("keydown", handleKeydown);

  // poll gaze status
  gazePoller = setInterval(pollGaze, 500);
  pollGaze();

  // small delay so the window finishes rendering before moving dots
  await new Promise((r) => setTimeout(r, 300));

  if (mode === "quick") {
    startQuickRecalibrate();
  } else {
    startFullCalibration();
  }
}

window.addEventListener("beforeunload", () => {
  if (gazePoller) clearInterval(gazePoller);
});

init();
