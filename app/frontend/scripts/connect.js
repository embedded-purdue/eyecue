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

function initInteractiveGlass() {
  const container = document.querySelector(".container");
  if (!container) return;

  const state = {
    pendingDrag: false,
    dragging: false,
    pointerId: null,
    startX: 0,
    startY: 0,
    baseX: 0,
    baseY: 0,
    x: 0,
    y: 0,
    bounds: null,
  };
  const dragThresholdPx = 6;

  const interactiveSelector = "input, select, button, textarea, option, a, label";

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function applyDragVars(x, y) {
    state.x = x;
    state.y = y;
    container.style.setProperty("--drag-x", `${x}px`);
    container.style.setProperty("--drag-y", `${y}px`);
  }

  function resetTiltAndOptics() {
    container.style.setProperty("--tilt-x", "0deg");
    container.style.setProperty("--tilt-y", "0deg");
    container.style.setProperty("--edge-opacity", "0.78");
    container.style.setProperty("--edge-blur", "0px");
    container.style.setProperty("--glare-opacity", "0.78");
    container.style.setProperty("--caustic-opacity", "0.74");
    container.style.setProperty("--prism-opacity", "0.72");
  }

  function computeBounds(rect, baseX, baseY) {
    const margin = 8;
    return {
      minX: baseX + (margin - rect.left),
      maxX: baseX + (window.innerWidth - margin - rect.right),
      minY: baseY + (margin - rect.top),
      maxY: baseY + (window.innerHeight - margin - rect.bottom),
    };
  }

  function clampToViewport(x, y) {
    const rect = container.getBoundingClientRect();
    const bounds = computeBounds(rect, x, y);
    return {
      x: clamp(x, bounds.minX, bounds.maxX),
      y: clamp(y, bounds.minY, bounds.maxY),
    };
  }

  container.addEventListener("pointerdown", (event) => {
    if (window.matchMedia("(max-width: 640px)").matches) {
      return;
    }
    if (event.button !== 0) {
      return;
    }
    if (event.target.closest(interactiveSelector)) {
      return;
    }

    state.pendingDrag = true;
    state.dragging = false;
    state.pointerId = event.pointerId;
    state.startX = event.clientX;
    state.startY = event.clientY;
    state.baseX = state.x;
    state.baseY = state.y;
    container.setPointerCapture(event.pointerId);
  });

  container.addEventListener("pointermove", (event) => {
    if (event.pointerId !== state.pointerId) {
      return;
    }

    if (state.pendingDrag && !state.dragging) {
      const dx = event.clientX - state.startX;
      const dy = event.clientY - state.startY;
      const distance = Math.hypot(dx, dy);
      if (distance < dragThresholdPx) {
        return;
      }
      state.pendingDrag = false;
      state.dragging = true;
      state.bounds = computeBounds(container.getBoundingClientRect(), state.baseX, state.baseY);
      container.classList.add("dragging");
    }

    if (!state.dragging) {
      return;
    }

    const bounds = state.bounds || { minX: -9999, maxX: 9999, minY: -9999, maxY: 9999 };
    const tentativeX = state.baseX + (event.clientX - state.startX);
    const tentativeY = state.baseY + (event.clientY - state.startY);
    const nextX = clamp(tentativeX, bounds.minX, bounds.maxX);
    const nextY = clamp(tentativeY, bounds.minY, bounds.maxY);

    applyDragVars(nextX, nextY);
  });

  function finishDrag(event) {
    if (event && state.pointerId !== null && event.pointerId !== state.pointerId) {
      return;
    }

    if (!state.dragging) {
      state.pendingDrag = false;
      if (state.pointerId !== null) {
        try {
          container.releasePointerCapture(state.pointerId);
        } catch (_err) {
          // ignore stale capture errors
        }
      }
      state.pointerId = null;
      return;
    }
    state.pendingDrag = false;
    state.dragging = false;
    container.classList.remove("dragging");
    resetTiltAndOptics();
    if (state.pointerId !== null) {
      try {
        container.releasePointerCapture(state.pointerId);
      } catch (_err) {
        // ignore stale capture errors
      }
    }
    state.pointerId = null;
  }

  container.addEventListener("pointerup", finishDrag);
  container.addEventListener("pointercancel", finishDrag);
  container.addEventListener("pointerleave", () => {
    if (!state.dragging) {
      resetTiltAndOptics();
    }
  });

  window.addEventListener("resize", () => {
    if (window.matchMedia("(max-width: 640px)").matches) {
      applyDragVars(0, 0);
      resetTiltAndOptics();
      return;
    }
    const clamped = clampToViewport(state.x, state.y);
    applyDragVars(clamped.x, clamped.y);
    resetTiltAndOptics();
  });

  resetTiltAndOptics();
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

async function init() {
  initInteractiveGlass();

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
