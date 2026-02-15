# EyeCue Frontend - Test Checklist

## Frame Labels Removed
- [x] Removed "Frame 6" from calibration.html
- [x] Removed "Frame 7" from calibration.js
- [x] Removed "Frame 9" from advanced-settings.html
- [x] Removed "Frame 10" from settings.html
- [x] Removed unused CSS for .frame-label and .frame-indicator

## Live Info View Implemented
- [x] Created live-info.html page
- [x] Created live-info.js script
- [x] Linked from settings page "Live Info View" button
- [x] Added back button navigation
- [x] Implemented Bluetooth connection check (non-blocking)
- [x] Shows terminal-style logs
- [x] Gracefully handles no device available
- [x] Checks backend serial connection status
- [x] App flow continues normally regardless of connection

## Navigation Flow Test

### 1. Welcome Page (`welcome.html`)
- [ ] Page loads with eye logo and "Welcome" title
- [ ] "Connect device with provided cable" subtitle visible
- [ ] Auto-navigates to connect.html after 2 seconds OR
- [ ] Manual click anywhere navigates immediately

### 2. Connection Form (`connect.html`)
- [ ] "Cue Connect" title with eye icon visible
- [ ] Network Name input field present
- [ ] Network Password input (masked) present
- [ ] Serial Port dropdown populated with available ports
- [ ] "Connect" button visible and clickable
- [ ] "Proceed With Wired Connection" link present
- [ ] Clicking link navigates to calibration.html
- [ ] Submitting form navigates to flashing.html with parameters

### 3. Flashing Progress (`flashing.html`)
- [ ] "Cue Connect" title visible
- [ ] "Flashing Network Information..." text present
- [ ] Animated progress bar visible and animating
- [ ] Sends POST request to /serial/connect
- [ ] Auto-navigates to calibration.html after ~3.5 seconds

### 4. Calibration Screen (`calibration.html`)
- [ ] Pre-calibration screen shows:
  - [ ] "Cue Connect" title with green eye icon
  - [ ] "First Time Calibration" heading
  - [ ] Blue cursor dot with "Cursor" label
  - [ ] "Enter Fullscreen" button
  - [ ] "Device Info" button (top right)
- [ ] Clicking "Enter Fullscreen" shows:
  - [ ] "Calibration Screen" header (orange)
  - [ ] 9 calibration nodes (3x3 grid)
  - [ ] First node highlighted in green with pulse animation
  - [ ] Instructions text at bottom
  - [ ] User cursor (blue dot) follows mouse
- [ ] Calibration interaction:
  - [ ] Only active (green) node is clickable
  - [ ] Clicking active node turns it blue (completed)
  - [ ] Next node becomes active (green)
  - [ ] Continues through all 9 nodes
  - [ ] After clicking all nodes, completion modal appears
- [ ] Completion modal:
  - [ ] "Calibration Complete" text
  - [ ] "Exit Fullscreen" button
  - [ ] Clicking exits fullscreen and navigates to settings.html
- [ ] Calibration data saved via POST /prefs/calibration

### 5. Settings Menu (`settings.html`)
- [ ] "Cue Connect" title with eye icon (green)
- [ ] "Settings Menu" heading
- [ ] Connection Mode toggle (WiFi/Wired) buttons
- [ ] Horizontal Sensitivity slider (0-100) with value display
- [ ] Vertical Sensitivity slider (0-100) with value display
- [ ] Four buttons visible:
  - [ ] "Recalibrate" - navigates to calibration.html
  - [ ] "Advanced Settings" - navigates to advanced-settings.html
  - [ ] "Live Info View" - navigates to live-info.html
  - [ ] "Flash WiFi Information" - navigates to connect.html
- [ ] "Device Info" button (top right) shows device status modal
- [ ] Settings persist to localStorage and backend
- [ ] No frame labels or indicators present

### 6. Advanced Settings Menu (`advanced-settings.html`)
- [ ] "Cue Connect" title visible
- [ ] "Advanced Settings Menu" heading
- [ ] Preference 1 dropdown with options
- [ ] Preference 2 dropdown with options
- [ ] Horizontal Sensitivity slider with value
- [ ] Vertical Sensitivity slider with value
- [ ] "Back" button navigates to settings.html
- [ ] "Device Info" button works
- [ ] Settings save properly
- [ ] No frame labels present

### 7. Live Info View (`live-info.html`) **NEW**
- [ ] Page loads with "Cue Connect" title
- [ ] "Live Info View" heading visible
- [ ] Connection status badge shows current state:
  - [ ] "Searching" (yellow) initially
  - [ ] "Connected" (green) if device found
  - [ ] "Disconnected" (red) if no device, with "offline mode" message
- [ ] Terminal display shows:
  - [ ] Timestamp-prefixed log entries
  - [ ] Color-coded messages (info/warning/error/success)
  - [ ] Bluetooth scan attempt logs
  - [ ] Backend serial connection check logs
  - [ ] Simulated data packets if connected
  - [ ] "Offline mode" message if no connection
- [ ] "Back" button navigates to settings.html
- [ ] "Device Info" button works
- [ ] **CRITICAL**: App never freezes or blocks even if:
  - [ ] Bluetooth is not supported
  - [ ] No devices are found
  - [ ] Backend is unreachable
  - [ ] User cancels device selection

## Button Functionality Tests

### All Pages
- [ ] No buttons are hidden or cut off
- [ ] All buttons have proper hover states
- [ ] No buttons freeze on click
- [ ] Button text is readable and not cut off
- [ ] Cursor changes to pointer on hover

### Primary Buttons (.btn-primary)
- [ ] Blue background (#4285f4)
- [ ] Hover effect: darker blue (#3367d6)
- [ ] Hover effect: slight lift (translateY)
- [ ] Smooth transitions (0.3s)

### Secondary Buttons (.btn-secondary)
- [ ] Light blue background (#e8f0fe)
- [ ] Blue text (#4285f4)
- [ ] Hover effect: darker background (#d2e3fc)

### Small Buttons (.btn-small)
- [ ] "Device Info" button always visible
- [ ] Proper sizing and padding
- [ ] Hover effects work

### Link Buttons (.link-button)
- [ ] "Proceed With Wired Connection" link styled correctly
- [ ] Blue text color
- [ ] Underline on hover
- [ ] No background

## Backend Integration Tests

### API Endpoints
- [ ] GET /health - returns {"status": "ok"}
- [ ] GET /serial/ports - returns list of available ports
- [ ] POST /serial/connect - accepts {port, ssid, password, baud}
- [ ] GET /serial/status - returns connection status
- [ ] GET /prefs - returns user preferences
- [ ] PUT /prefs - saves preferences
- [ ] POST /prefs/calibration - saves calibration data

### Data Persistence
- [ ] Settings save to localStorage
- [ ] Settings save to backend (~/.eyecue/prefs.json)
- [ ] Settings load on page refresh
- [ ] Calibration data persists
- [ ] WiFi credentials stored (if saved)

## Visual/Rendering Tests

### Layout
- [ ] No elements overlap or cut off
- [ ] Proper centering on all pages
- [ ] Responsive to window resizing
- [ ] Consistent spacing and padding

### Animations
- [ ] Progress bar animation in flashing.html
- [ ] Pulse animation on active calibration node
- [ ] Status dot pulse animation
- [ ] Smooth transitions on hover
- [ ] No janky or stuttering animations

### Typography
- [ ] All text is readable
- [ ] Proper font sizes and weights
- [ ] Consistent font family across pages
- [ ] No text overflow

### Colors
- [ ] Consistent color scheme throughout
- [ ] Good contrast for readability
- [ ] Status colors clear (green=success, yellow=warning, red=error)

## Error Handling

### Connection Failures
- [ ] Backend unreachable: app continues to work
- [ ] No serial ports: dropdown shows appropriate message
- [ ] Connection timeout: error displayed but app not frozen
- [ ] Bluetooth unavailable: informative message, no crash

### Edge Cases
- [ ] Empty form submission: validation prevents
- [ ] Invalid port selection: handled gracefully
- [ ] Rapid button clicking: no double navigation
- [ ] Browser back button: works as expected
- [ ] Page refresh: state preserved where appropriate

## Performance

### Load Times
- [ ] Pages load quickly (<1 second)
- [ ] No blocking operations on page load
- [ ] Background tasks don't freeze UI

### Resource Usage
- [ ] No memory leaks from page navigation
- [ ] Event listeners properly cleaned up
- [ ] No excessive console errors

## Cross-Page Consistency

### Navigation Header
- [ ] "Cue Connect" title consistent across pages
- [ ] Eye icon consistent (except welcome page)
- [ ] Device Info button present where expected

### Styling
- [ ] Button styles consistent
- [ ] Input field styles consistent
- [ ] Color scheme consistent
- [ ] Spacing and padding consistent

## Final Integration Test

### Complete Flow (Happy Path)
1. [ ] Start at welcome.html
2. [ ] Wait for auto-navigation or click
3. [ ] Arrive at connect.html
4. [ ] Fill in Network Name: "TestWiFi"
5. [ ] Fill in Password: "test123"
6. [ ] Select a serial port (or auto-detect)
7. [ ] Click "Connect"
8. [ ] Arrive at flashing.html with progress animation
9. [ ] Auto-navigate to calibration.html
10. [ ] Click "Enter Fullscreen"
11. [ ] Click all 9 calibration nodes in sequence
12. [ ] Completion modal appears
13. [ ] Click "Exit Fullscreen"
14. [ ] Arrive at settings.html
15. [ ] Adjust sliders (verify values update)
16. [ ] Click "Live Info View"
17. [ ] Verify connection status and terminal logs
18. [ ] Click "Back"
19. [ ] Return to settings.html
20. [ ] Click "Advanced Settings"
21. [ ] Change preferences
22. [ ] Click "Back"
23. [ ] Return to settings.html
24. [ ] Click "Recalibrate"
25. [ ] Return to calibration screen
26. [ ] Complete calibration again
27. [ ] Exit to settings

### Alternative Paths
- [ ] Welcome → Connect → "Wired Connection" → Calibration
- [ ] Settings → "Flash WiFi" → Connect Form
- [ ] Any Device Info button → Modal displays → Close → Continue

## Bugs Found
(List any issues discovered during testing)

- None

## Notes
- Web Bluetooth API requires HTTPS or localhost
- Bluetooth connection is optional and non-blocking
- App fully functional without any hardware connected
- Backend server must be running for full functionality
- All preferences save to both localStorage and backend for redundancy
