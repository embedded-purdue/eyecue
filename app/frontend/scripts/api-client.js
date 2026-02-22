(function initEyeApi() {
  const API_BASE = 'http://127.0.0.1:5001';

  async function request(path, options = {}) {
    const {
      method = 'GET',
      body,
      timeoutMs = 5000,
      headers = {},
    } = options;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(`${API_BASE}${path}`, {
        method,
        headers: {
          'Content-Type': 'application/json',
          ...headers,
        },
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });

      let payload = null;
      try {
        payload = await response.json();
      } catch (parseErr) {
        payload = { ok: false, error: `Invalid JSON response for ${path}` };
      }

      if (!response.ok || !payload.ok) {
        const message = (payload && payload.error) || `HTTP ${response.status}`;
        throw new Error(message);
      }

      return payload.data;
    } finally {
      clearTimeout(timeout);
    }
  }

  window.eyeApi = {
    apiBase: API_BASE,
    request,
    health: () => request('/health'),
    bootstrap: () => request('/app/bootstrap'),
    getRuntimeState: () => request('/runtime/state'),
    startRuntime: (payload) => request('/runtime/start', { method: 'POST', body: payload }),
    stopRuntime: () => request('/runtime/stop', { method: 'POST', body: {} }),
    listSerialPorts: () => request('/serial/ports'),
    serialStatus: () => request('/serial/status'),
    connectSerialCompat: (payload) => request('/serial/connect', { method: 'POST', body: payload }),
    disconnectSerialCompat: () => request('/serial/disconnect', { method: 'POST', body: {} }),
    getPrefs: () => request('/prefs'),
    updatePrefs: (payload) => request('/prefs', { method: 'PUT', body: payload }),
    startCalibrationSession: (payload) => request('/calibration/session/start', { method: 'POST', body: payload || {} }),
    getCalibrationSession: () => request('/calibration/session'),
    submitCalibrationNode: (payload) => request('/calibration/session/node', { method: 'POST', body: payload }),
    completeCalibrationSession: (payload) => request('/calibration/session/complete', { method: 'POST', body: payload }),
  };
})();
