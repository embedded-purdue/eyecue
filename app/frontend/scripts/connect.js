/**
 * connect.js - Minimal one-page connection flow.
 */

const stateEls = {
  connectScreen: document.getElementById("connectScreen"),
  pairingScreen: document.getElementById("pairingScreen"),
  runtimeScreen: document.getElementById("runtimeScreen"),
  pairingPhase: document.getElementById("pairingPhaseText"),
  phase: document.getElementById("phaseText"),
  bypass: document.getElementById("bypassText"),
  tracking: document.getElementById("trackingText"),
  ssid: document.getElementById("ssidText"),
  serial: document.getElementById("serialText"),
  ip: document.getElementById("ipText"),
  stream: document.getElementById("streamText"),
  lastFrame: document.getElementById("lastFrameText"),
  alertsCount: document.getElementById("alertsCountText"),
  error: document.getElementById("errorText"),
  frames: document.getElementById("framesText"),
  log: document.getElementById("statusLog"),
};

let pollingTimer = null;
let renderedAlertId = 0;
let lastPollErrorMessage = "";
let bootstrapLoaded = false;
let currentScreenMode = "connect";
let runtimeReadyStreak = 0;
let pairingTransitionLockUntil = 0;
let activeResizeEdge = null;

const RESIZE_MIN_WIDTH = 860;
const RESIZE_MIN_HEIGHT = 920;

function initInteractiveGlass() {
  const container = document.querySelector(".container");
  if (!container) return;

  // Dragging is handled by CSS app-region on the container.
  // Keep this hook for future visual effects, but do not add motion here.
}

function bindWindowResizeHandles() {
  if (!window.electronAPI) return;

  const handles = document.querySelectorAll(".window-edge-resize, .resize-handle");
  handles.forEach((handle) => {
    const edge = handle.dataset.edge;
    if (!edge) return;

    handle.addEventListener("mousedown", (event) => {
      event.preventDefault();
      event.stopPropagation();
      activeResizeEdge = edge;
      const resizeEdge = edge === "top-left" || edge === "top-right" || edge === "bottom-left" || edge === "bottom-right"
        ? edge
        : edge;
      window.electronAPI.beginWindowResize(
        resizeEdge,
        event.screenX,
        event.screenY,
        RESIZE_MIN_WIDTH,
        RESIZE_MIN_HEIGHT,
      );

      const onMove = (moveEvent) => {
        if (!activeResizeEdge) return;
        window.electronAPI.moveWindowResize(
          moveEvent.screenX,
          moveEvent.screenY,
          RESIZE_MIN_WIDTH,
          RESIZE_MIN_HEIGHT,
        );
      };

      const endResize = () => {
        if (!activeResizeEdge) return;
        activeResizeEdge = null;
        window.electronAPI.endWindowResize();
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", endResize);
      };

      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", endResize, { once: true });
      window.addEventListener("blur", endResize, { once: true });
    });
  });
}

function renderPorts(ports, selectedPort) {
  const select = document.getElementById("serialPort");
  select.innerHTML = '<option value="">Select Port</option>';
  (ports || []).forEach((port) => {
    const option = document.createElement("option");
    option.value = port.device;
    option.textContent = `${port.device} - ${port.description || "Unknown"}`;
    if (selectedPort && selectedPort === port.device) {
      option.selected = true;
    }
    select.appendChild(option);
  });
}

function formatTime(ts_ms) {
  if (!Number.isFinite(ts_ms)) {
    return "--:--:--";
  }
  const d = new Date(ts_ms);

  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  const ss = String(d.getSeconds()).padStart(2, "0");

  return `${hh}:${mm}:${ss}`;
}

function appendAlert(alert) {
  if (!alert || !alert.id || alert.id <= renderedAlertId) return;
  renderedAlertId = alert.id;
  const entry = document.createElement("div");
  const formattedTime = formatTime(alert.ts_ms);
  entry.className = `status-entry ${alert.level || "info"}`;
  entry.textContent = `${alert.message || "status update"} [${formattedTime}]`;
  stateEls.log.prepend(entry);
}

function appendClientAlert(level, message) {
  const entry = document.createElement("div");
  entry.className = `status-entry ${level || "error"}`;
  entry.textContent = message || "";
  stateEls.log.prepend(entry);
}

function setScreen(mode) {
  const showConnect = mode === "connect";
  const showPairing = mode === "pairing";
  const showRuntime = mode === "runtime";

  if (stateEls.connectScreen) {
    stateEls.connectScreen.classList.toggle("screen-hidden", !showConnect);
  }
  if (stateEls.pairingScreen) {
    stateEls.pairingScreen.classList.toggle("screen-hidden", !showPairing);
  }
  if (stateEls.runtimeScreen) {
    stateEls.runtimeScreen.classList.toggle("screen-hidden", !showRuntime);
  }

  currentScreenMode = mode;
}

function phaseToScreen(phase) {
  const value = String(phase || "idle");
  if (value === "idle") return "connect";
  if (value === "error") return "connect";
  if (value === "streaming" || value === "stream_retrying") return "runtime";
  return "pairing";
}

function renderRuntime(runtime) {
  const phase = runtime.phase || "idle";
  stateEls.phase.textContent = `Phase: ${phase}`;
  if (stateEls.pairingPhase) {
    stateEls.pairingPhase.textContent = `Phase: ${phase}`;
  }
  const bypassEnabled = runtime.phase === "bypass_mode" || runtime.ssid === "(bypass)";
  if (stateEls.bypass) {
    stateEls.bypass.textContent = `Bypass Mode: ${bypassEnabled ? "on" : "off"}`;
  }
  if (stateEls.tracking) {
    stateEls.tracking.textContent = `Tracking Enabled: ${runtime.tracking_enabled ? "on" : "off"}`;
  }
  if (stateEls.ssid) {
    stateEls.ssid.textContent = `Network: ${runtime.ssid || "--"}`;
  }
  if (stateEls.serial) {
    stateEls.serial.textContent = `Serial Port: ${runtime.serial_port || "--"}`;
  }
  if (stateEls.ip) {
    stateEls.ip.textContent = `ESP32 IP: ${runtime.esp32_ip || "--"}`;
  }
  if (stateEls.stream) {
    stateEls.stream.textContent = `Stream URL: ${runtime.stream_url || "--"}`;
  }
  if (stateEls.lastFrame) {
    stateEls.lastFrame.textContent = `Last Frame: ${formatTime(runtime.last_frame_ts_ms)}`;
  }
  if (stateEls.error) {
    stateEls.error.textContent = `Last Error: ${runtime.last_error || "none"}`;
  }
  stateEls.frames.textContent = `Frames Processed: ${runtime.frames_processed || 0}`;

  const alerts = runtime.alerts || [];
  if (stateEls.alertsCount) {
    stateEls.alertsCount.textContent = `Alerts: ${alerts.length}`;
  }
  for (let i = 0; i < alerts.length; i += 1) {
    appendAlert(alerts[i]);
  }

  const targetScreen = phaseToScreen(phase);
  const now = Date.now();
  const isRuntimePhase = phase === "streaming" || phase === "stream_retrying";

  if (isRuntimePhase) {
    runtimeReadyStreak += 1;
    pairingTransitionLockUntil = 0;
  } else {
    runtimeReadyStreak = 0;
  }

  let stableScreen = targetScreen;

  // Keep pairing visible briefly while connect request is in flight to prevent idle/connect flicker.
  if (
    currentScreenMode === "pairing" &&
    targetScreen === "connect" &&
    now < pairingTransitionLockUntil
  ) {
    stableScreen = "pairing";
  }

  // Require two consecutive runtime polls before switching from pairing to runtime.
  if (
    currentScreenMode === "pairing" &&
    targetScreen === "runtime" &&
    runtimeReadyStreak < 2
  ) {
    stableScreen = "pairing";
  }

  // Once runtime is visible, do not bounce back to pairing on transient reconnect phases.
  if (currentScreenMode === "runtime" && targetScreen === "pairing") {
    stableScreen = "runtime";
  }

  // Screen persistence rules:
  // - Pairing stays visible unless runtime is actually ready or user cancels.
  // - Runtime stays visible unless user explicitly exits.
  // - Connect may auto-enter pairing/runtime only when app boots into active states.
  if (currentScreenMode === "pairing") {
    if (!(targetScreen === "runtime" && runtimeReadyStreak >= 2)) {
      stableScreen = "pairing";
    }
  }

  if (currentScreenMode === "runtime") {
    stableScreen = "runtime";
  }

  if (stableScreen !== currentScreenMode) {
    setScreen(stableScreen);
  }
}

async function refreshRuntime() {
  if (!bootstrapLoaded) {
    try {
      await loadBootstrap();
      return;
    } catch (_err) {
      // backend may still be launching; poll loop will retry
    }
  }

  try {
    const runtime = await window.eyeApi.getRuntimeState();
    lastPollErrorMessage = "";
    renderRuntime(runtime);
    const toggle = document.getElementById("trackingToggle");
    if (toggle && toggle.checked !== Boolean(runtime.tracking_enabled)) {
      toggle.checked = Boolean(runtime.tracking_enabled);
    }
    if (typeof updateCalibrationStatus === "function") {
      updateCalibrationStatus();
    }
  } catch (err) {
    const message = `Runtime poll failed: ${err.message}`;
    if (message !== lastPollErrorMessage) {
      appendClientAlert("error", message);
      lastPollErrorMessage = message;
    }
  }
}

function setConnectBusy(isBusy) {
  const connectButton = document.getElementById("connectButton");
  const bypassButton = document.getElementById("bypassButton");
  if (connectButton) {
    connectButton.disabled = Boolean(isBusy);
  }
  if (bypassButton) {
    bypassButton.disabled = Boolean(isBusy);
  }
}

async function loadBootstrap() {
  const data = await window.eyeApi.bootstrap();
  const prefs = data.prefs || {};

  document.getElementById("networkName").value = prefs.wifi_ssid || "";
  document.getElementById("networkPassword").value = prefs.wifi_password || "";
  renderPorts(data.serial_ports || [], prefs.last_serial_port || "");
  renderRuntime(data.runtime || {});

  const toggle = document.getElementById("trackingToggle");
  toggle.checked = Boolean(data.tracking_enabled);

  const phase = (data.runtime && data.runtime.phase) || "idle";
  setScreen(phaseToScreen(phase));
  bootstrapLoaded = true;
}

document
  .getElementById("connectForm")
  .addEventListener("submit", async (event) => {
    event.preventDefault();
    const ssid = document.getElementById("networkName").value.trim();
    const password = document.getElementById("networkPassword").value;
    const serialPort = document.getElementById("serialPort").value;

    if (!ssid || !password || !serialPort) {
      appendClientAlert(
        "error",
        "Network name, password, and serial port are required.",
      );
      return;
    }

    try {
      setConnectBusy(true);
      runtimeReadyStreak = 0;
      pairingTransitionLockUntil = Date.now() + 5000;
      setScreen("pairing");
      const runtime = await window.eyeApi.connectRuntime({
        ssid,
        password,
        serial_port: serialPort,
        baud: 115200,
      });
      renderRuntime(runtime);
    } catch (err) {
      appendClientAlert("error", `Connection failed: ${err.message}`);
      setScreen("pairing");
    } finally {
      setConnectBusy(false);
    }
  });

document.getElementById("bypassButton").addEventListener("click", async () => {
  const ssid = document.getElementById("networkName").value.trim();
  const password = document.getElementById("networkPassword").value;
  const serialPort = document.getElementById("serialPort").value;

  try {
    setConnectBusy(true);
    runtimeReadyStreak = 0;
    pairingTransitionLockUntil = Date.now() + 5000;
    setScreen("pairing");
    const runtime = await window.eyeApi.bypassRuntime({
      ssid,
      password,
      serial_port: serialPort,
      baud: 115200,
    });
    renderRuntime(runtime);
    appendClientAlert(
      "warning",
      "Bypass mode enabled: serial pairing was skipped. You can continue without a paired device.",
    );
  } catch (err) {
    appendClientAlert("error", `Bypass failed: ${err.message}`);
    setScreen("pairing");
  } finally {
    setConnectBusy(false);
  }
});

document
  .getElementById("trackingToggle")
  .addEventListener("change", async (event) => {
    try {
      const runtime = await window.eyeApi.setTracking(
        Boolean(event.target.checked),
      );
      renderRuntime(runtime);
    } catch (err) {
      appendClientAlert("error", `Tracking update failed: ${err.message}`);
    }
  });

document.getElementById("backButton").addEventListener("click", () => {
  document.getElementById("stopButton").click();
});

document.getElementById("cancelPairingButton").addEventListener("click", async () => {
  try {
    await window.eyeApi.stopRuntime();
  } catch (_err) {
    // best-effort cancellation
  }
  setScreen("connect");
});

document.getElementById("stopButton").addEventListener("click", async () => {
  try {
    const runtime = await window.eyeApi.stopRuntime();
    renderRuntime(runtime);
    setScreen("connect");
  } catch (err) {
    appendClientAlert("error", `Stop failed: ${err.message}`);
  }
});

document.getElementById("calibrateButton").addEventListener("click", () => {
  if (window.electronAPI && window.electronAPI.openCalibration) {
    window.electronAPI.openCalibration("full");
  } else {
    appendClientAlert("error", "Calibration window requires Electron.");
  }
});

document.getElementById("quickCalibrateButton").addEventListener("click", () => {
  if (window.electronAPI && window.electronAPI.openCalibration) {
    window.electronAPI.openCalibration("quick");
  } else {
    appendClientAlert("error", "Calibration window requires Electron.");
  }
});

async function updateCalibrationStatus() {
  try {
    const data = await window.eyeApi.getCalibrationState();
    const statusEl = document.getElementById("calibrationStatus");
    if (statusEl) {
      if (data && data.calibrated) {
        statusEl.textContent = "✓ Calibrated";
        statusEl.classList.add("calibrated");
      } else {
        statusEl.textContent = "Not calibrated";
        statusEl.classList.remove("calibrated");
      }
    }
  } catch {
    // ignore — backend may not support it yet
  }
}

async function init() {
  initInteractiveGlass();
  bindWindowResizeHandles();

  try {
    await loadBootstrap();
  } catch (err) {
    appendClientAlert("error", `Bootstrap failed: ${err.message}`);
  }

  pollingTimer = setInterval(refreshRuntime, 1000);
}

window.addEventListener("beforeunload", () => {
  if (pollingTimer) {
    clearInterval(pollingTimer);
  }
});

init();
