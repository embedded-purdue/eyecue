/**
 * main.js - Electron main process
 * Owns Flask lifecycle for the desktop app.
 */

const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');

const BACKEND_HOST = '127.0.0.1';
const BACKEND_PORT = 5001;
const BACKEND_BASE = `http://${BACKEND_HOST}:${BACKEND_PORT}`;

let mainWindow = null;
let backendProcess = null;
let backendOwned = false;

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
          'Content-Type': 'application/json',
          'Content-Length': payload ? Buffer.byteLength(payload) : 0,
        },
        timeout: 1200,
      },
      (res) => {
        let data = '';
        res.on('data', (chunk) => {
          data += chunk;
        });
        res.on('end', () => {
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
      }
    );

    req.on('timeout', () => {
      req.destroy(new Error('request timeout'));
    });
    req.on('error', reject);

    if (payload) {
      req.write(payload);
    }
    req.end();
  });
}

async function checkBackendHealth() {
  try {
    const payload = await httpRequestJson('GET', '/health');
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

  const projectRoot = path.resolve(__dirname, '..', '..');
  backendProcess = spawn('python3', ['-m', 'app.app'], {
    cwd: projectRoot,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  backendOwned = true;

  backendProcess.stdout.on('data', (chunk) => {
    process.stdout.write(`[backend] ${chunk}`);
  });
  backendProcess.stderr.on('data', (chunk) => {
    process.stderr.write(`[backend] ${chunk}`);
  });
  backendProcess.on('exit', (code, signal) => {
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
  mainWindow = new BrowserWindow({
    width: 860,
    height: 860,
    minWidth: 700,
    minHeight: 700,
    resizable: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js'),
      enableBlinkFeatures: 'WebBluetooth',
    },
    titleBarStyle: 'default',
    title: 'EyeCue',
  });

  mainWindow.loadFile(path.join(__dirname, 'pages', 'welcome.html'));

  if (process.argv.includes('--debug')) {
    mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

async function shutdownBackend() {
  try {
    await httpRequestJson('POST', '/runtime/stop', {});
  } catch (err) {
    // Best-effort shutdown request.
  }

  if (backendOwned && backendProcess && !backendProcess.killed) {
    backendProcess.kill('SIGTERM');
  }
}

app.whenReady().then(async () => {
  try {
    await ensureBackend();
  } catch (err) {
    process.stderr.write(`${String(err)}\n`);
  }

  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('before-quit', () => {
  shutdownBackend();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
