# EyeCue Testing Checklist (Current Desktop App)

This checklist is aligned to the current single-page Electron UI:

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

- [ ] App opens directly in Electron (no manual Flask launch required)
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

Some root scripts and docs under `old_files/` or historical checklists are legacy/experimental.
For desktop validation, use this checklist and Electron workflows above.
- [ ] No CORS errors
- [ ] No failed API calls (or graceful fallbacks)

### Expected Console Logs
- [ ] API calls show success messages
- [ ] Calibration data logged when saved
- [ ] Settings changes logged when saved

---

## Visual/UI Tests

### Rendering
- [ ] All pages render without layout issues
- [ ] Buttons don't overlap or disappear
- [ ] Text is readable and properly sized
- [ ] Sliders are functional and smooth
- [ ] Animations are smooth (progress bar, node pulse)
- [ ] Modal appears on top of content
- [ ] Fullscreen overlay covers entire screen

### Responsive Behavior
- [ ] Pages work at different window sizes
- [ ] Calibration grid maintains aspect ratio
- [ ] Buttons remain clickable
- [ ] Text doesn't overflow

---

## Edge Cases

### Empty/Invalid Data
- [ ] Connect form with empty fields → Shows error
- [ ] No serial ports available → Handles gracefully
- [ ] Backend offline → Frontend still navigates (demo mode)
- [ ] Invalid preference values → Uses defaults

### Rapid Actions
- [ ] Clicking nodes rapidly → Responds correctly
- [ ] Quickly navigating between pages → No errors
- [ ] Rapid slider adjustments → Updates smoothly

### Browser Compatibility
- [ ] Test in Chrome/Edge
- [ ] Test in Firefox
- [ ] Test in Safari (if on Mac)
- [ ] Fullscreen may not work in all browsers (acceptable)

---

## Performance Checks

- [ ] Page loads are fast (<1 second)
- [ ] No memory leaks (check DevTools Performance tab)
- [ ] Smooth animations
- [ ] No lag when interacting with UI
- [ ] API calls complete quickly (<500ms locally)

---

## Known Issues / Expected Behavior

✅ **Fullscreen may not activate** - Some browsers block fullscreen, but calibration still works in windowed mode

✅ **Backend connection optional** - App works in demo mode if backend is down

✅ **Password in sessionStorage** - More secure than URL, cleared on tab close

✅ **localStorage + Backend** - Dual persistence for offline capability

---

## Sign-Off Checklist

### Critical Functionality
- [ ] ✅ Can complete full flow from Welcome to Settings
- [ ] ✅ All 9 calibration nodes are clickable in sequence
- [ ] ✅ Settings are saved and persist
- [ ] ✅ Navigation works in all directions
- [ ] ✅ No page crashes or freezes
- [ ] ✅ Backend API responds correctly
- [ ] ✅ All buttons are functional

### User Experience
- [ ] ✅ Flow is intuitive and smooth
- [ ] ✅ Visual feedback is clear
- [ ] ✅ Error messages are helpful
- [ ] ✅ Progress is visible (counters, animations)

### Code Quality
- [ ] ✅ No console errors
- [ ] ✅ Clean code structure
- [ ] ✅ Proper error handling
- [ ] ✅ Comments and documentation

---

## Final Verification

Run this complete test sequence without interruption:

1. Start backend: `./restart_server.sh`
2. Start Electron: `cd app/frontend && npm start`
3. **Welcome** → Wait or click
4. **Connect** → Fill form → Submit
5. **Flashing** → Wait for auto-navigation
6. **Calibration** → Click "Enter Fullscreen"
7. **9-Dot Grid** → Click all 9 nodes in sequence
8. **Completion** → Click "Exit Fullscreen"
9. **Settings** → Adjust sliders, toggle modes
10. **Advanced Settings** → Change preferences
11. **Back to Settings** → Verify values preserved
12. **Recalibrate** → Do calibration again
13. **Back to Settings** → Check persistence
14. **Flash WiFi** → Go through connection flow again

✅ **PASSED** if all steps complete without errors or freezing

---

## Bug Report Template

If issues found, document as follows:

**Bug:** [Brief description]  
**Page:** [Which page/screen]  
**Steps to Reproduce:**  
1. ...  
2. ...  

**Expected:** [What should happen]  
**Actual:** [What actually happens]  
**Console Errors:** [Copy from browser console]  
**Screenshot:** [If applicable]
