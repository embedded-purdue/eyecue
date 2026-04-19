# EyeCue Electron Frontend (Minimal)

Single-page Electron UI for the prototype pipeline.

## UI Contents

- Network configuration form (SSID/password/serial port)
- Connect button
- Cursor-tracking toggle
- Backend alert/status area

## Runtime Model

- Electron starts the bundled backend binary (`dist/eyecue-backend` in dev, `Resources/eyecue-backend` when packaged).
- If no backend binary is available, Electron falls back to `python3 -m app.app` for development.
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
