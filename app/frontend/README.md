# EyeCue Electron Frontend

Electron renderer for the EyeCue setup/calibration/settings flow.

## Runtime model

- Electron main process starts Flask (`python3 -m app.app`) on launch.
- Frontend pages call Flask JSON APIs at `http://127.0.0.1:5001`.
- Backend owns runtime state, agent lifecycle, calibration session state, and preferences.

## Main pages

1. `welcome.html` - startup bootstrap routing
2. `connect.html` - serial/wired connection menu
3. `flashing.html` - runtime start transition
4. `calibration.html` - backend-backed calibration session
5. `settings.html` - primary settings menu
6. `advanced-settings.html` - advanced preferences
7. `live-info.html` - runtime monitor

## Scripts

- `scripts/api-client.js` shared API wrapper for all pages
- page-level scripts call `window.eyeApi.*` methods only

## Run

```bash
cd app/frontend
npm install
npm start
```

Use debug mode:

```bash
npm run dev
```
