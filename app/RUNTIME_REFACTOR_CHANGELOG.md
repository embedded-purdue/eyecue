# Runtime Refactor Changelog

Date: 2026-02-19

This file records what was changed during the diagram-aligned runtime refactor so future agents can quickly understand scope and avoid rework.

## Summary

Implemented a backend-centric runtime model where Flask owns state and agent lifecycle, with Electron launching and supervising Flask. Added serial/cursor thread agents, calibration session APIs, ingest APIs, and rewired renderer pages to use shared backend contracts.

## Added files

### Backend config/services
- `app/config.py`
- `app/services/runtime_store.py`
- `app/services/agent_supervisor.py`
- `app/services/serial_agent.py`
- `app/services/cursor_agent.py`
- `app/services/calibration_service.py`
- `app/services/runtime_context.py`

### Backend routes
- `app/routes/app_state.py`
- `app/routes/runtime.py`
- `app/routes/internal.py`
- `app/routes/ingest.py`
- `app/routes/calibration.py`

### Frontend shared API
- `app/frontend/scripts/api-client.js`

### Tests
- `tests/test_runtime_store.py`
- `tests/test_calibration_service.py`
- `tests/test_routes.py`

## Modified files (core)

### Backend
- `app/app.py`
  - unified app factory and blueprint registration
- `run_server.py`
  - now uses unified app factory
- `app/routes/serial.py`
  - compatibility shim behavior + runtime-backed status
- `app/routes/prefs.py`
  - calibration shim forwards to new calibration service
- `app/routes/cursor.py`
  - fixed import/runtime behavior and runtime-store ingestion
- `app/serial_connect.py`
  - graceful handling when `pyserial` is unavailable
- `app/services/serial_manager.py`
  - converted into compatibility wrapper
- `app/services/__init__.py`
  - simplified package init
- `requirements.txt`
  - added `flask-cors`, `requests`, `pyserial`, `pyautogui`

### Frontend
- `app/frontend/main.js`
  - Electron now starts Flask and checks health
- `app/frontend/scripts/welcome.js`
- `app/frontend/scripts/connect.js`
- `app/frontend/scripts/flashing.js`
- `app/frontend/scripts/calibration.js`
- `app/frontend/scripts/settings.js`
- `app/frontend/scripts/advanced-settings.js`
- `app/frontend/scripts/live-info.js`
- `app/frontend/pages/*.html`
  - each page now loads `scripts/api-client.js`
- `app/frontend/README.md`
  - updated runtime notes

## Important behavior decisions implemented

- Serial Agent and Cursor Agent are separate threads.
- Agents communicate with Flask via localhost HTTP internal endpoints.
- Runtime source selection uses single active source + stale-data fallback.
- Calibration now has backend state machine (`idle`, `running`, `completed`, `aborted`).
- Frontend prefers backend state over local browser storage.

## Compatibility behavior retained

- `POST /serial/connect`
- `POST /serial/disconnect`
- `POST /prefs/calibration`

These route to new runtime/calibration internals to avoid immediate breakage.

## Known caveat

`serial.connected` currently indicates serial transport/session connected, not guaranteed verified cursor JSON stream. A future change should add explicit stream-verification fields.

## Suggested next tasks for future agents

1. Add `serial.transport_connected` vs `serial.stream_verified` fields and update UI labels.
2. Add timeout/heartbeat logic for stream verification (e.g., stale when no valid serial cursor sample > N seconds).
3. Add integration tests for serial and wireless fallback transitions.
4. Add optional persistence for last successful wireless device metadata.
