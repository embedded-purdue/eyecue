# Testing the Live Info View

## Quick Start

### 1. Start the Backend Server

```bash
cd /Users/williamzhang/Documents/GitHub/eyecue
./restart_server.sh
```

Or manually:
```bash
.venv/bin/python run_server.py
```

Wait for the message: `Running on http://127.0.0.1:5001`

### 2. Start the Electron App

```bash
cd app/frontend
npm start
```

### 3. Navigate to Live Info View

1. App opens to Welcome screen
2. Click through to Connect page (or wait 2 seconds)
3. Click "Proceed With Wired Connection" (skip WiFi setup for now)
4. Complete calibration (click all 9 nodes)
5. You'll reach Settings page
6. Click **"Live Info View"** button

---

## What You Should See

### Without ESP32 Hardware:

#### Connection Status Badge:
- **Yellow "Searching..."** for ~2 seconds (initial check)
- **Red "No Device Connected"** afterwards

#### Connection Details Panel:
```
WiFi: Not Connected
Serial: Disconnected
Camera: Not Available
```

#### Activity Log (Terminal):
```
[14:30:15] EyeCue Live Info View initialized
[14:30:15] ════════════════════════════════════════
[14:30:15] ESP32 Camera Server Connection Monitor
[14:30:15] This page shows real-time connection status
[14:30:15] ════════════════════════════════════════
[14:30:15] Live monitoring started
[14:30:15] Polling device status every 2 seconds...
[14:30:16] No ESP32 device detected
[14:30:16] Waiting for device connection...
```

The terminal will update every 2 seconds with real connection checks.

---

## Testing Scenarios

### Scenario 1: Normal Operation (No Hardware)

**Expected Behavior:**
- Status badge shows "No Device Connected" (red)
- Info panel shows all fields as unavailable
- Terminal logs connection check attempts
- No crashes or freezes
- Page remains stable

**Test Actions:**
1. Resize window - layout should adapt
2. Wait 30 seconds - no memory issues
3. Click "Device Info" button - shows status modal
4. Click "Back to Settings" - returns smoothly

### Scenario 2: Backend Server Down

**Steps:**
1. Stop the backend: `pkill -f run_server.py`
2. Refresh the Live Info View page

**Expected Behavior:**
- Status badge shows "Backend Connection Error" (red)
- Info panel shows "Unable to fetch" for all fields
- Terminal logs:
  ```
  [14:32:10] Cannot connect to backend server
  [14:32:10] Error: Failed to fetch
  [14:32:10] Make sure run_server.py is running on port 5001
  ```
- App doesn't crash, continues polling

### Scenario 3: Backend Comes Back Online

**Steps:**
1. With Live Info View open and backend down
2. Start backend: `.venv/bin/python run_server.py`
3. Wait 2-4 seconds

**Expected Behavior:**
- Status badge updates to "No Device Connected"
- Info panel updates with connection details
- Terminal logs successful reconnection

### Scenario 4: With ESP32 Connected (When Hardware Available)

**Prerequisites:**
- ESP32 connected via USB
- From Settings, go to Connect page
- Enter WiFi credentials
- Flash to device

**Expected Behavior:**
- Status badge shows "ESP32 Connected via Serial" (green)
- Info panel shows:
  ```
  WiFi: Connected | SSID: YourNetwork | IP: 192.168.1.100
  Serial: Connected | Port: /dev/cu.usbserial-0001 | Baud: 115200
  Camera: Ready | Size: QVGA | Quality: 10
  ```
- Terminal logs:
  ```
  [14:35:20] ESP32 device connected on /dev/cu.usbserial-0001
  [14:35:20] WiFi connected: YourNetwork (192.168.1.100)
  [14:35:20] Camera server ready for streaming
  ```

---

## Stability Tests

### Window Resizing
1. Normal size → Mobile (400px width)
   - ✅ Text wraps properly
   - ✅ Buttons stack vertically
   - ✅ Terminal remains readable
   - ✅ No horizontal scrolling

2. Extreme sizes (1920x1080, 320x568)
   - ✅ Layout adapts gracefully
   - ✅ No element overflow
   - ✅ All buttons accessible

### Memory Test
1. Leave page open for 5 minutes
   - ✅ Terminal limited to 100 lines
   - ✅ No performance degradation
   - ✅ No browser slowdown
   - ✅ CPU usage remains low

### Navigation Test
1. Navigate to Live Info View
2. Wait 10 seconds (polling active)
3. Click "Back to Settings"
4. Return to Live Info View multiple times
   - ✅ No duplicate polling intervals
   - ✅ Clean initialization each time
   - ✅ No memory leaks
   - ✅ Smooth transitions

### Error Resilience
1. Disconnect network (airplane mode)
2. Live Info View should show backend error
3. Reconnect network
4. Should recover automatically within 2 seconds

---

## Debugging

### Check Browser Console

Open DevTools (F12) and check for errors:

**Should NOT see:**
- ❌ Uncaught TypeError
- ❌ Failed to fetch (repeatedly)
- ❌ Memory warnings

**Should see:**
- ✅ Normal fetch requests to `/serial/status`
- ✅ Clean 200 responses or expected errors

### Check Backend Logs

In terminal running `run_server.py`:

**Should see:**
```
127.0.0.1 - - [15/Feb/2026 14:30:16] "GET /serial/status HTTP/1.1" 200 -
127.0.0.1 - - [15/Feb/2026 14:30:18] "GET /serial/status HTTP/1.1" 200 -
127.0.0.1 - - [15/Feb/2026 14:30:20] "GET /serial/status HTTP/1.1" 200 -
```

**Every 2 seconds:**
- Request to `/serial/status`
- 200 OK response
- No errors or exceptions

### Verify API Response

In terminal:
```bash
curl http://127.0.0.1:5001/serial/status | python3 -m json.tool
```

**Expected Output (No Device):**
```json
{
  "ok": true,
  "data": {
    "connected": false,
    "port": null,
    "baud_rate": 115200,
    "last_error": null,
    "wifi_connected": false,
    "wifi_ssid": null,
    "wifi_ip": null,
    "camera_ready": false,
    "frame_size": null,
    "jpeg_quality": null
  }
}
```

---

## Known Behavior (Not Bugs)

### 1. Initial "Searching" State
- Lasts 2-4 seconds on first load
- Normal: Backend needs time to respond
- Transitions to "Disconnected" or "Connected"

### 2. WiFi IP Shows Placeholder
- When device connected but no real ESP32 data
- Shows: `192.168.1.100`
- **Why:** Backend doesn't yet parse ESP32 serial JSON status
- **Future:** Will show real IP from device

### 3. Terminal Scrolls Continuously
- New logs appear at bottom
- Auto-scrolls to show latest
- Old lines disappear after 100 entries
- Normal behavior for live monitoring

### 4. Status Badge Pulses
- Animated pulse effect
- Indicates active monitoring
- Visual feedback system is working

---

## Success Criteria

✅ **Stability:** Page never crashes or freezes  
✅ **Responsiveness:** Works on all screen sizes  
✅ **Truthfulness:** Shows actual backend connection status  
✅ **Memory:** No leaks, limited terminal lines  
✅ **Performance:** Smooth polling every 2 seconds  
✅ **Error Handling:** Graceful when backend unavailable  
✅ **Navigation:** Clean transitions, proper cleanup  

---

## Troubleshooting

### "Backend Connection Error" Won't Go Away

**Check:**
1. Is backend running? `lsof -i :5001`
2. Can you access it? `curl http://127.0.0.1:5001/health`
3. Firewall blocking port 5001?

**Fix:**
```bash
cd /Users/williamzhang/Documents/GitHub/eyecue
.venv/bin/python run_server.py
```

### Page Freezes or Becomes Unresponsive

**Likely Cause:** Old polling interval not cleaned up

**Fix:**
1. Close Electron app completely
2. Restart: `npm start`
3. Should work normally

### Terminal Not Updating

**Check:**
1. Open DevTools (F12) → Console
2. Look for JavaScript errors
3. Check Network tab for `/serial/status` requests

**Fix:**
1. Hard refresh: Cmd+Shift+R (Mac) or Ctrl+Shift+R (Windows)
2. Restart Electron app

### Device Info Modal Shows Old Data

**Normal Behavior:** Modal fetches fresh data on click

**If stale:**
1. Backend cache issue
2. Restart backend server
3. Try again

---

## Next Steps

Once you have ESP32 hardware:

1. **Connect device via USB**
2. **Flash WiFi credentials** from Connect page
3. **View in Live Info** to see real connection status
4. **Enhance backend** to parse JSON status from ESP32:
   - Real WiFi IP address
   - Actual camera settings
   - Frame rate, quality metrics
   - Signal strength (RSSI)

The infrastructure is ready - just needs real device data!
