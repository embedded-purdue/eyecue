/**
 * main.js - Electron main process
 * Owns Flask lifecycle for the desktop app.
 */

const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");
const fs = require("fs");

const BACKEND_HOST = "127.0.0.1";
const BACKEND_PORT = 5051;
const BACKEND_BASE = `http://${BACKEND_HOST}:${BACKEND_PORT}`;

let mainWindow = null;
let backendProcess = null;
let backendOwned = false;
let quitInProgress = false;
let shutdownPromise = null;
const activeResizeSessions = new Map();

function resolveBackendLaunch() {
  if (app.isPackaged) {
    return {
      exec: path.join(process.resourcesPath, "eyecue-backend"),
      args: [],
      cwd: process.resourcesPath,
      mode: "packaged-binary",
    };
  }

  const projectRoot = path.resolve(__dirname, "..", "..");
  const devMode = String(process.env.EYECUE_DEV_BACKEND_MODE || "python").toLowerCase();
  const overrideBinary = process.env.EYECUE_BACKEND_BINARY;
  const distBinary = path.join(projectRoot, "dist", "eyecue-backend");

  if (devMode === "binary" && overrideBinary && fs.existsSync(overrideBinary)) {
    return {
      exec: overrideBinary,
      args: [],
      cwd: projectRoot,
      mode: "env-binary",
    };
  }

  if (devMode === "binary" && fs.existsSync(distBinary)) {
    return {
      exec: distBinary,
      args: [],
      cwd: projectRoot,
      mode: "dev-binary",
    };
  }

  const venvPython = path.join(projectRoot, "env", "bin", "python");
  return {
    exec: fs.existsSync(venvPython) ? venvPython : "python3",
    args: ["-m", "app.app"],
    cwd: projectRoot,
    mode: "python-fallback",
  };
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function httpRequestJson(method, endpoint, body) {
  return new Promise((resolve, reject) => {
    const payload = body ? JSON.stringify(body) : null;
    const req = http.request(
      {
        hostname: BACKEND_HOST,
        port: BACKEND_PORT,
        path: endpoint,
        method,
        headers: {
          "Content-Type": "application/json",
          "Content-Length": payload ? Buffer.byteLength(payload) : 0,
        },
        timeout: 1200,
      },
      (res) => {
        let data = "";
        res.on("data", (chunk) => {
          data += chunk;
        });
        res.on("end", () => {
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`HTTP ${res.statusCode}`));
            return;
          }
          try {
            resolve(JSON.parse(data));
          } catch (err) {
            reject(err);
          }
        });
      },
    );

    req.on("timeout", () => {
      req.destroy(new Error("request timeout"));
    });
    req.on("error", reject);

    if (payload) {
      req.write(payload);
    }
    req.end();
  });
}

async function checkBackendHealth() {
  try {
    const payload = await httpRequestJson("GET", "/health");
    return Boolean(payload && payload.ok);
  } catch (err) {
    return false;
  }
}

async function waitForBackend(timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await checkBackendHealth()) {
      return true;
    }
    await delay(250);
  }
  return false;
}

function startBackendProcess() {
  if (backendProcess && !backendProcess.killed) {
    return;
  }

  const launch = resolveBackendLaunch();
  process.stdout.write(`[backend] launch mode=${launch.mode} exec=${launch.exec}\n`);

  backendProcess = spawn(launch.exec, launch.args, {
    cwd: launch.cwd,
    stdio: ["ignore", "pipe", "pipe"],
  });
  backendOwned = true;

  backendProcess.stdout.on("data", (chunk) => {
    process.stdout.write(`[backend] ${chunk}`);
  });
  backendProcess.stderr.on("data", (chunk) => {
    process.stderr.write(`[backend] ${chunk}`);
  });
  backendProcess.on("exit", (code, signal) => {
    process.stdout.write(`[backend] exited code=${code} signal=${signal}\n`);
    backendProcess = null;
  });
}

async function ensureBackend() {
  const alreadyRunning = await checkBackendHealth();
  if (alreadyRunning) {
    backendOwned = false;
    return;
  }

  startBackendProcess();
  const healthy = await waitForBackend(20000);
  if (!healthy) {
    throw new Error(`Backend did not become healthy at ${BACKEND_BASE}`);
  }
}

function createWindow() {
  const appIconPath = path.join(__dirname, "assets", "eyecue-logo.png");
  const isMac = process.platform === "darwin";
  mainWindow = new BrowserWindow({
    width: 980,
    height: 860,
    minWidth: 860,
    minHeight: 720,
    resizable: true,
    frame: false,
    titleBarStyle: "hidden",
    transparent: true,
    backgroundColor: "#00000000",
    icon: fs.existsSync(appIconPath) ? appIconPath : undefined,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
      enableBlinkFeatures: "WebBluetooth",
    },
    title: "EyeCue",
  });

  mainWindow.loadFile(path.join(__dirname, "pages", "connect.html"));

  if (process.argv.includes("--debug")) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

ipcMain.on("window-control", (event, action) => {
  const senderWindow = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  if (!senderWindow || senderWindow.isDestroyed()) {
    return;
  }

  if (action === "minimize") {
    senderWindow.minimize();
    return;
  }

  if (action === "maximize-toggle") {
    if (senderWindow.isMaximized()) {
      senderWindow.unmaximize();
    } else {
      senderWindow.maximize();
    }
    return;
  }

  if (action === "close") {
    senderWindow.close();
  }
});

ipcMain.on("window-resize-start", (event, payload) => {
  const senderWindow = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  if (!senderWindow || senderWindow.isDestroyed()) {
    return;
  }

  const edge = String(payload?.edge || "");
  if (!edge) {
    return;
  }

  const bounds = senderWindow.getBounds();
  activeResizeSessions.set(senderWindow.id, {
    edge,
    startX: Number(payload?.screenX) || 0,
    startY: Number(payload?.screenY) || 0,
    bounds,
  });
});

ipcMain.on("window-resize-move", (event, payload) => {
  const senderWindow = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  if (!senderWindow || senderWindow.isDestroyed()) {
    return;
  }

  const session = activeResizeSessions.get(senderWindow.id);
  if (!session) {
    return;
  }

  const currentX = Number(payload?.screenX) || 0;
  const currentY = Number(payload?.screenY) || 0;
  const deltaX = currentX - session.startX;
  const deltaY = currentY - session.startY;

  const minWidth = Number(payload?.minWidth) || 860;
  const minHeight = Number(payload?.minHeight) || 920;

  const nextBounds = { ...session.bounds };

  if (session.edge.includes("left")) {
    const maxShift = session.bounds.width - minWidth;
    const shift = Math.max(Math.min(deltaX, maxShift), -maxShift);
    nextBounds.x = session.bounds.x + shift;
    nextBounds.width = session.bounds.width - shift;
  }

  if (session.edge.includes("right")) {
    nextBounds.width = Math.max(minWidth, session.bounds.width + deltaX);
  }

  if (session.edge.includes("top")) {
    const maxShift = session.bounds.height - minHeight;
    const shift = Math.max(Math.min(deltaY, maxShift), -maxShift);
    nextBounds.y = session.bounds.y + shift;
    nextBounds.height = session.bounds.height - shift;
  }

  if (session.edge.includes("bottom")) {
    nextBounds.height = Math.max(minHeight, session.bounds.height + deltaY);
  }

  senderWindow.setBounds(nextBounds, false);
});

ipcMain.on("window-resize-end", (event) => {
  const senderWindow = BrowserWindow.fromWebContents(event.sender) || mainWindow;
  if (!senderWindow) {
    return;
  }

  activeResizeSessions.delete(senderWindow.id);
});

async function shutdownBackend() {
  if (shutdownPromise) {
    return shutdownPromise;
  }

  shutdownPromise = (async () => {
    try {
      await httpRequestJson("POST", "/runtime/stop", {});
    } catch (err) {
      // Best-effort shutdown request.
    }

    if (backendOwned && backendProcess && !backendProcess.killed) {
      backendProcess.kill("SIGTERM");
      const exited = await waitForBackendExit(3000);
      if (!exited && backendProcess && !backendProcess.killed) {
        backendProcess.kill("SIGKILL");
        await waitForBackendExit(1000);
      }
    }
  })();

  return shutdownPromise;
}

function waitForBackendExit(timeoutMs) {
  return new Promise((resolve) => {
    if (!backendProcess || backendProcess.killed) {
      resolve(true);
      return;
    }

    const proc = backendProcess;
    const timer = setTimeout(() => {
      cleanup();
      resolve(false);
    }, timeoutMs);

    function onExit() {
      cleanup();
      resolve(true);
    }

    function cleanup() {
      clearTimeout(timer);
      if (proc) {
        proc.removeListener("exit", onExit);
      }
    }

    proc.once("exit", onExit);
  });
}

app.whenReady().then(() => {
  createWindow();

  ensureBackend().catch((err) => {
    process.stderr.write(`${String(err)}\n`);
  });

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("before-quit", (event) => {
  if (quitInProgress) {
    return;
  }
  event.preventDefault();
  quitInProgress = true;
  shutdownBackend().finally(() => {
    app.exit(0);
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
