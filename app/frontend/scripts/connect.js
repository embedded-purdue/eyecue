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
  frames: document.getElementById("framesText"),
  log: document.getElementById("statusLog"),
};

let pollingTimer = null;
let renderedAlertId = 0;
let lastPollErrorMessage = "";

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
  stateEls.frames.textContent = `Frames Processed: ${runtime.frames_processed || 0}`;

  const alerts = runtime.alerts || [];
  for (let i = 0; i < alerts.length; i += 1) {
    appendAlert(alerts[i]);
  }

  setScreen(phaseToScreen(phase));
}

async function refreshRuntime() {
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
      setScreen("connect");
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
    setScreen("connect");
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
