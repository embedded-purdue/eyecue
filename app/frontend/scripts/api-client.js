(function initEyeApi() {
  const API_BASE = 'http://127.0.0.1:5051';

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
    listSerialPorts: () => request('/serial/ports'),
    getRuntimeState: () => request('/runtime/state'),
    connectRuntime: (payload) => request('/runtime/connect', { method: 'POST', body: payload }),
    bypassRuntime: (payload = {}) => request('/runtime/bypass', { method: 'POST', body: payload }),
    setTracking: (enabled) => request('/runtime/tracking', { method: 'POST', body: { enabled: Boolean(enabled) } }),
    stopRuntime: () => request('/runtime/stop', { method: 'POST', body: {} }),
    getCalibrationState: () => request('/runtime/calibrate/state'),
  };
})();
