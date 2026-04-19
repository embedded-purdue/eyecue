# EyeCue Electron Frontend (Minimal)

Single-page Electron UI for the prototype pipeline.

## UI Contents

- Network configuration form (SSID/password/serial port)
- Connect button
- Cursor-tracking toggle
- Backend alert/status area

## Runtime Model

- In development, Electron starts the Python backend (`env/bin/python -m app.app` when available).
- In packaged builds, Electron starts the bundled backend binary (`Resources/eyecue-backend`).
- You can opt into binary testing in development with `npm run start:desktop:binary`.
- Renderer calls Flask APIs at `http://127.0.0.1:5051`.
- Renderer polls `/runtime/state` for live status and alerts.

## Main Files

- `main.js` (Electron lifecycle + backend process)
- `pages/connect.html`
- `scripts/connect.js`
- `scripts/api-client.js`
- `styles/main.css`

## Run

```bash
cd app/frontend
npm install
npm run start:desktop
```

## Build

```bash
cd app/frontend
npm run make
```
