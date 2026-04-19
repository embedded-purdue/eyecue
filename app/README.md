# EyeCue Flask Backend

## Build

Run `./build.sh` from the project root.

This builds:
- `dist/eyecue-backend` (PyInstaller backend binary)
- Electron distributables in `app/frontend/out/make/`

Equivalent commands:

```bash
bash build_backend.sh
cd app/frontend && npm run make
```

## Testing

Make sure you do not have Anaconda installed. Copy `.env.example` to a new `.env` file.
If you are simulating a webcam, set `BYPASS_SERIAL` to `true`.

Setup the virtual environment (venv) by running `python3 -m venv env` from the project root.
Then, install all dependencies by running `pip install -r requirements.txt`.

Resolve dependencies by running `source env/bin/activate` and start the webcam simulator
with `python app-tests/serve_webcam.py`. Then, start the desktop app with:

```bash
cd app/frontend
npm run start:desktop
```

## Overview

This backend implements one prototype pipeline:

`Network credentials -> ESP32 serial provisioning -> MJPEG stream -> CV processing -> optional cursor control`

## Start

```bash
cd app/frontend
npm run start:desktop
```

Developer fallback (only if backend binary is missing):

```bash
python3 -m app.app
```

Server default:

- Host: `127.0.0.1`
- Port: `5051`

Health check:

```bash
curl http://127.0.0.1:5051/health
```

## API

### Bootstrap and Serial

- `GET /app/bootstrap`
- `GET /serial/ports`

### Runtime

- `POST /runtime/connect`
  - JSON: `ssid`, `password`, `serial_port`, optional `baud`
- `POST /runtime/bypass`
  - JSON: optional `ssid`, `password`, `serial_port`, optional `baud`
  - Skips serial provisioning and starts runtime in bypass mode.
- `GET /runtime/state`
- `POST /runtime/tracking`
  - JSON: `enabled` (boolean)
- `POST /runtime/stop`

## Runtime State Shape

`/runtime/state` returns:

- `phase`
- `ssid`
- `serial_port`
- `esp32_ip`
- `stream_url`
- `tracking_enabled`
- `frames_processed`
- `last_frame_ts_ms`
- `last_error`
- `alerts` (`[{id, ts_ms, level, message}]`)

## Notes

- MJPEG path attempts start with `http://<esp32_ip>/stream`.
- Additional fallback paths can be configured via `EYE_MJPEG_PATHS`.
- Tracking toggle is session-only and defaults to disabled at app launch.
