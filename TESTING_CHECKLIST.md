# EyeCue Testing Checklist

## Pre-Test Setup

✅ **Backend Server Running**
```bash
./restart_server.sh
# Verify: curl http://127.0.0.1:5001/health
```

✅ **Electron App**
```bash
cd app/frontend
npm install
npm start
```

---

## Test Flow: Complete User Journey

### 1. Welcome Screen
- [ ] Page loads with eye logo
- [ ] "Connect device with provided cable" text visible
- [ ] Auto-navigates to Connect page after 2 seconds
- [ ] OR Click anywhere to immediately advance
- [ ] No console errors

**Expected Result:** Smooth transition to Connect page

---

### 2. Connection Form
- [ ] "Cue Connect" title with eye icon displays
- [ ] Network Name input field is visible and functional
- [ ] Network Password input field is visible and functional (password masked)
- [ ] Serial Port dropdown is populated with available ports
- [ ] "Auto-detect" option is present in dropdown
- [ ] "Connect" button is visible and clickable
- [ ] "Proceed With Wired Connection" link is visible

**Test Cases:**

#### 2a. Form Validation
- [ ] Try submitting empty form → Error message appears
- [ ] Fill Network Name only → Error message appears
- [ ] Fill all fields → Form submits successfully

#### 2b. Serial Port Loading
- [ ] Check browser console for `/serial/ports` API call
- [ ] Verify serial ports are fetched from backend
- [ ] Dropdown shows real port names (e.g., `/dev/cu.Bluetooth-Incoming-Port`)

#### 2c. Form Submission
- [ ] Fill in all fields with test data:
  - Network Name: `TestNetwork`
  - Password: `TestPassword123`
  - Port: Select any or "Auto-detect"
- [ ] Click "Connect"
- [ ] Password is stored in sessionStorage (check DevTools)
- [ ] Navigates to Flashing page with URL parameters

**Expected Result:** URL should be `flashing.html?ssid=TestNetwork&port=...`

---

### 3. Flashing Progress Screen
- [ ] "Cue Connect" title displays
- [ ] "Flashing Network Information..." text visible
- [ ] Animated progress bar is animating (blue bar moving)
- [ ] Page automatically calls `/serial/connect` API
- [ ] Check browser console for API call and response
- [ ] After 1.5-3.5 seconds, auto-navigates to Calibration

**Test Cases:**

#### 3a. Backend Connection (with device)
- [ ] If ESP32 is connected, credentials are sent
- [ ] Success message in console logs
- [ ] Navigates after 1.5 seconds

#### 3b. Backend Connection (no device)
- [ ] If no device or backend error, still proceeds
- [ ] Shows console error but doesn't break
- [ ] Navigates after 3.5 seconds

**Expected Result:** Automatic navigation to Calibration page

---

### 4. Calibration Screen (Pre-Fullscreen)
- [ ] "Cue Connect" title with green eye icon
- [ ] "First Time Calibration" heading
- [ ] Blue cursor dot preview with "Cursor" label
- [ ] "Enter Fullscreen" button is visible and clickable
- [ ] "Device Info" button in top-right corner

#### 4a. Device Info Button
- [ ] Click "Device Info" button
- [ ] Alert/modal shows device status
- [ ] Status displays connection state, port, errors
- [ ] Can close and continue

#### 4b. Enter Calibration
- [ ] Click "Enter Fullscreen" button
- [ ] Overlay appears with gray background
- [ ] "Calibration Screen" header at top
- [ ] "Frame 6" label in top-left
- [ ] 3×3 grid of 9 nodes appears
- [ ] First node (top-left) is highlighted green and pulsing
- [ ] All other nodes are gray and inactive (dim)
- [ ] Instructions at bottom show current node
- [ ] Blue cursor dot tracks mouse movement
- [ ] Fullscreen mode attempts to activate (may not work in all browsers)

---

### 5. Calibration Grid (9-Dot Sequence)
- [ ] **Node 1 (Top-Left):** Green, pulsing, clickable
- [ ] Click Node 1 → Turns blue (completed)
- [ ] **Node 2 (Top-Center):** Becomes green, pulsing
- [ ] Instruction text updates to "Active Node: top center (2/9)"
- [ ] Click Node 2 → Turns blue
- [ ] **Node 3 (Top-Right):** Becomes green
- [ ] Continue through all 9 nodes

**Full Sequence:**
1. Top-Left → 2. Top-Center → 3. Top-Right
4. Middle-Left → 5. Middle-Center → 6. Middle-Right
7. Bottom-Left → 8. Bottom-Center → 9. Bottom-Right

**Test Each Node:**
- [ ] Only active node is green and pulsing
- [ ] Completed nodes stay blue
- [ ] Inactive nodes stay gray and dim
- [ ] Can't click inactive nodes (pointer-events: none)
- [ ] Clicking wrong node does nothing
- [ ] Instruction text updates with each node
- [ ] Counter shows progress (1/9, 2/9, ... 9/9)
- [ ] Blue cursor tracks mouse throughout

---

### 6. Calibration Completion
After clicking all 9 nodes:
- [ ] All nodes turn blue
- [ ] "Frame 7" label appears (updates from "Frame 6")
- [ ] Instructions text disappears
- [ ] White modal appears with "Calibration Complete"
- [ ] "Exit Fullscreen" button visible
- [ ] API call to `/prefs/calibration` is made
- [ ] Check browser console for successful save
- [ ] Backend receives calibration data

#### 6a. Exit to Settings
- [ ] Click "Exit Fullscreen" button
- [ ] Fullscreen mode exits
- [ ] Navigates to Settings Menu
- [ ] No errors in console

---

### 7. Settings Menu
- [ ] "Cue Connect" title with green eye icon
- [ ] "Settings Menu" heading
- [ ] "Device Info" button in top-right
- [ ] Connection Mode section with WiFi/Wired toggle
- [ ] WiFi button is selected (blue background)
- [ ] Horizontal Sensitivity slider (0-100)
- [ ] Vertical Sensitivity slider (0-100)
- [ ] Slider values display next to sliders
- [ ] Four buttons visible:
  - [ ] "Recalibrate"
  - [ ] "Advanced Settings"
  - [ ] "Live Info View"
  - [ ] "Flash WiFi Information"
- [ ] "860 × 860, Frame 10" indicator at bottom-right

**Test Cases:**

#### 7a. Connection Mode Toggle
- [ ] WiFi button is active (blue)
- [ ] Click "Wired" → Becomes active (blue)
- [ ] Click "WiFi" → Returns to active (blue)
- [ ] Selection is saved to localStorage
- [ ] Selection is saved to backend (check `/prefs`)

#### 7b. Sensitivity Sliders
- [ ] Drag Horizontal slider → Value updates
- [ ] Number next to slider updates in real-time
- [ ] Drag Vertical slider → Value updates
- [ ] Values are saved to localStorage
- [ ] Values are saved to backend
- [ ] Verify: check browser console for API calls

#### 7c. Recalibrate Button
- [ ] Click "Recalibrate"
- [ ] Navigates back to Calibration page
- [ ] Can complete calibration again
- [ ] Returns to Settings after completion

#### 7d. Advanced Settings Button
- [ ] Click "Advanced Settings"
- [ ] Navigates to Advanced Settings page
- [ ] No console errors

#### 7e. Live Info View Button
- [ ] Click "Live Info View"
- [ ] Alert/modal appears (placeholder)
- [ ] Can close and continue

#### 7f. Flash WiFi Information Button
- [ ] Click "Flash WiFi Information"
- [ ] Navigates to Connect page
- [ ] Can fill out form and proceed through flow again

#### 7g. Device Info Button
- [ ] Click "Device Info"
- [ ] Alert shows device status
- [ ] Shows connection mode (WiFi/Wired)
- [ ] Shows connection status
- [ ] Shows port and errors

---

### 8. Advanced Settings Menu
- [ ] "Cue Connect" title with green eye icon
- [ ] "Advanced Settings Menu" heading
- [ ] "Device Info" button in top-right
- [ ] "Preference 1" dropdown with options
- [ ] "Preference 2" dropdown with options
- [ ] Horizontal Sensitivity slider (0-100)
- [ ] Vertical Sensitivity slider (0-100)
- [ ] "Back" button visible and functional
- [ ] "Frame 9" indicator at bottom-right

**Test Cases:**

#### 8a. Preference Dropdowns
- [ ] Click Preference 1 dropdown → Options visible
- [ ] Select a different option → Saves automatically
- [ ] Click Preference 2 dropdown → Options visible
- [ ] Select a different option → Saves automatically
- [ ] Values saved to localStorage
- [ ] Values saved to backend

#### 8b. Sensitivity Sliders
- [ ] Sliders show same values as Settings page
- [ ] Drag sliders → Values update
- [ ] Changes sync with Settings page
- [ ] Values persist across navigation

#### 8c. Back Button
- [ ] Click "Back" button
- [ ] Navigates to Settings Menu
- [ ] Settings values are preserved

#### 8d. Device Info Button
- [ ] Click "Device Info"
- [ ] Alert shows same info as Settings page

---

## Navigation Tests

### Bidirectional Navigation
- [ ] Settings → Advanced Settings → Back → Settings (preserves state)
- [ ] Settings → Recalibrate → Complete → Settings (preserves state)
- [ ] Settings → Flash WiFi → Connect → Flashing → Calibration → Settings
- [ ] Any page → Device Info → Close → Same page (no state loss)

### State Persistence
- [ ] Set sliders in Settings → Navigate away → Return → Values preserved
- [ ] Set sliders in Advanced Settings → Navigate away → Return → Values preserved
- [ ] Complete calibration → Check backend → Data saved
- [ ] Refresh any page → Check if backend prefs load correctly

---

## Backend API Tests

### Test All Endpoints
```bash
# Health check
curl http://127.0.0.1:5001/health

# List serial ports
curl http://127.0.0.1:5001/serial/ports

# Get preferences
curl http://127.0.0.1:5001/prefs

# Update preferences (test)
curl -X PUT http://127.0.0.1:5001/prefs \
  -H "Content-Type: application/json" \
  -d '{"horizontal_sensitivity": 75}'

# Verify update
curl http://127.0.0.1:5001/prefs

# Check saved file
cat ~/.eyecue/prefs.json
```

### API Tests Checklist
- [ ] `/health` returns `{"status": "ok"}`
- [ ] `/serial/ports` returns list of ports
- [ ] `/prefs` GET returns all preferences
- [ ] `/prefs` PUT updates preferences
- [ ] `/prefs/calibration` POST saves calibration data
- [ ] `~/.eyecue/prefs.json` file is created and updated
- [ ] CORS headers are present (Access-Control-Allow-Origin: *)

---

## Browser Console Checks

### No Errors
- [ ] No red errors in Console tab
- [ ] No 404 errors for missing resources
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
