# EyeCue Testing Checklist (Current Desktop App)

This checklist matches the current single-page Electron UI flow:

`Connect -> Pairing -> Runtime`

## 1. Pre-Test Setup

### Install dependencies

```bash
# repo root
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt

# frontend
cd app/frontend
npm install
```

### Launch desktop app (Electron-first)

```bash
cd app/frontend
npm run start:desktop
```

`start:desktop` builds `dist/eyecue-backend` and starts Electron.

## 2. Connect Screen

- [ ] App opens in Electron (no manual Flask launch required)
- [ ] Logo/background/glass UI renders
- [ ] Network Name, Network Password, Serial Port inputs are interactive
- [ ] Connect Device button works
- [ ] Bypass Connect button works

Validation:

- [ ] Empty connect form shows validation error
- [ ] Serial port list populates from `/serial/ports`

## 3. Pairing Screen

- [ ] Connect Device transitions to Pairing
- [ ] Bypass Connect transitions to Pairing
- [ ] Pairing phase text updates with backend state
- [ ] Cancel Pairing returns to Connect and stops runtime best-effort

## 4. Runtime Screen

- [ ] Runtime screen appears when phase reaches streaming/retrying
- [ ] Tracking toggle calls `/runtime/tracking` and updates state
- [ ] Status panel receives alerts and frame count updates
- [ ] Stop Runtime returns to Connect
- [ ] Back To Connect returns to Connect via stop flow

## 5. Backend Health/API Smoke Tests

With app running:

```bash
curl http://127.0.0.1:5051/health
curl http://127.0.0.1:5051/app/bootstrap
curl http://127.0.0.1:5051/runtime/state
```

Expected:

- [ ] `/health` returns `{ "ok": true }`
- [ ] `/app/bootstrap` returns prefs, ports, runtime shape
- [ ] `/runtime/state` returns phase/tracking/alerts structure

## 6. Packaging Smoke Test

```bash
# repo root
./build.sh
```

Expected:

- [ ] `dist/eyecue-backend` exists
- [ ] Electron artifacts exist under `app/frontend/out/make/`

## 7. Regression Checks

- [ ] No dead buttons (all visible actions transition to valid states)
- [ ] No console exceptions on connect/bypass/stop/tracking
- [ ] App closes cleanly (backend stops when Electron quits)

## Legacy Note

Some root scripts and docs under `old_files/` are legacy/experimental.
For desktop validation, use this checklist and Electron workflows above.
