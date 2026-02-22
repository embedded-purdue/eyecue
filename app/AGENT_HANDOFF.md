# EyeCue Agent Handoff

Last updated: 2026-02-19

This document is for future coding agents and maintainers. It summarizes the current runtime architecture, key contracts, and practical implementation notes after the Electron + Flask runtime refactor.

## 1) High-level architecture

- Electron (`app/frontend/main.js`) owns backend lifecycle.
- Electron starts Flask via `python3 -m app.app` when the desktop app launches.
- Electron checks `/health` before loading the UI.
- Flask is the source of truth for runtime state, agent lifecycle, calibration state, and preferences.

### Runtime components

- `RuntimeStore` (`app/services/runtime_store.py`)
  - Thread-safe global state
  - Tracks serial/wireless/cursor/agent metrics
  - Handles active-source fallback when data gets stale
- `AgentSupervisor` (`app/services/agent_supervisor.py`)
  - Starts/stops Serial Agent and Cursor Agent threads
- `SerialAgent` (`app/services/serial_agent.py`)
  - Opens serial transport and forwards serial cursor/stats to Flask internal endpoints via localhost HTTP
- `CursorAgent` (`app/services/cursor_agent.py`)
  - Polls internal Flask cursor endpoints at capped rate and applies cursor updates (if enabled)
- `CalibrationService` (`app/services/calibration_service.py`)
  - Session state machine for calibration lifecycle

## 2) API surface

### Electron/public-facing

- `GET /health`
- `GET /app/bootstrap`
- `GET /runtime/state`
- `POST /runtime/start`
- `POST /runtime/stop`
- `GET /serial/ports`
- `POST /serial/connect` (compat shim)
- `POST /serial/disconnect` (compat shim)
- `GET /serial/status`
- `GET /prefs`
- `PUT /prefs`
- `POST /prefs/calibration` (compat shim)
- `GET /calibration/session`
- `POST /calibration/session/start`
- `POST /calibration/session/node`
- `POST /calibration/session/complete`

### Wireless ingest

- `POST /ingest/wireless/cursor`
- `POST /ingest/wireless/stats`

### Internal localhost-only

- `POST /internal/ingest/cursor`
- `POST /internal/ingest/stats`
- `GET /internal/cursor/latest`
- `GET /internal/cursor/params`

## 3) Frontend flow

All frontend pages use shared client `app/frontend/scripts/api-client.js`.

Flow implemented:
- Startup decision: `/app/bootstrap`
  - new user -> `welcome.html`
  - existing + connected -> `settings.html`
  - existing + not connected -> `connect.html`
- Connection menu -> `flashing.html` -> `/runtime/start`
- First-time path goes to `calibration.html`
- Returning user path goes to `settings.html`

## 4) Connection status semantics (important)

Current semantics:
- `serial.connected = true` means the serial transport was opened and Serial Agent reported connected.
- It does **not** strictly mean valid cursor telemetry has already been received from ESP32.
- Data flow truth comes from cursor sample presence/rate (`cursor.last_sample`, `cursor.sample_rate_hz`) and active source behavior.

Practical implication:
- UI may show "connected" while no useful serial JSON cursor payload has arrived yet.
- This is expected with current implementation and should be treated as "transport connected" rather than "stream verified".

## 5) Key files to inspect first

- App factory and blueprint wiring:
  - `app/app.py`
- Runtime state and source fallback:
  - `app/services/runtime_store.py`
- Agent lifecycle:
  - `app/services/agent_supervisor.py`
- Agent loops:
  - `app/services/serial_agent.py`
  - `app/services/cursor_agent.py`
- Bootstrap logic:
  - `app/routes/app_state.py`
- Runtime control:
  - `app/routes/runtime.py`
- Frontend startup and page API usage:
  - `app/frontend/main.js`
  - `app/frontend/scripts/api-client.js`

## 6) Running and testing

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run backend only:

```bash
python3 -m app.app
```

Run Electron app:

```bash
cd app/frontend
npm start
```

Run tests:

```bash
python3 -m unittest discover tests
```

## 7) Known gaps / next improvements

- Add explicit distinction between:
  - serial transport connected
  - serial data streaming verified
- Add stronger serial health checks (heartbeat/ACK format from firmware)
- Tighten internal endpoint auth if deployed beyond local desktop usage
- Expand integration tests with mocked serial and mocked wireless ingest
