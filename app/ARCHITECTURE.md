## Architecture

- Electron launches Flask and opens one page: `app/frontend/pages/connect.html`.
- Flask exposes minimal APIs for:
  - app bootstrap (`/app/bootstrap`)
  - serial port list (`/serial/ports`)
  - runtime control (`/runtime/connect`, `/runtime/state`, `/runtime/tracking`, `/runtime/stop`)
- `PipelineController` (`app/services/pipeline_controller.py`) is the only runtime orchestrator.

## Pipeline

1. User submits SSID/password/serial port.
2. Flask opens serial, sends line command:
   - `WIFI_CONFIG {"ssid":"...","password":"...","nonce":"..."}`
3. Flask waits for serial responses:
   - `ACK WIFI_CONFIG <nonce>`
   - `OK <ip>`
   - `ERR <domain> <reason>`
4. Flask closes serial and starts MJPEG pull from `http://<ip>/stream` (with fallback paths).
5. Each MJPEG frame runs through `ContourPupilFrameProcessor`.
6. Cursor movement is applied only when tracking toggle is enabled.

## Runtime State Contract

State fields:

- `phase`
- `ssid`
- `serial_port`
- `esp32_ip`
- `stream_url`
- `tracking_enabled`
- `frames_processed`
- `last_frame_ts_ms`
- `last_error`
- `alerts`

Alert entry shape:

- `id`
- `ts_ms`
- `level`
- `message`

## Important Files

- `app/services/pipeline_controller.py`
- `app/routes/runtime.py`
- `app/routes/app_state.py`
- `app/routes/serial.py`
- `app/frontend/pages/connect.html`
- `app/frontend/scripts/connect.js`
- `app/frontend/scripts/api-client.js`

## Run

Desktop app (recommended):

```bash
cd app/frontend
npm run start:desktop
```

Backend-only fallback:

```bash
python3 -m app.app
```

Tests:

```bash
/Users/williamzhang/Documents/GitHub/eyecue/env/bin/python -m unittest discover -s app-tests -p "test_*.py"
```
