# EyeCue Frontend - User Flow Documentation

### 1. **Welcome Screen** (`welcome.html`)
- **Purpose**: Initial greeting and device connection prompt
- **Duration**: Auto-advances after 2 seconds or on click
- **Next**: Navigates to Connect page

### 2. **Connection Form** (`connect.html`)
- **Purpose**: Configure WiFi credentials and serial port
- **Features**:
  - Network Name input
  - Network Password input (masked)
  - Serial Port selection (auto-populated from backend)
  - Auto-detect option for port selection
- **Backend Integration**:
  - `GET /serial/ports` - Fetches available serial ports
  - Form data prepared for transmission
- **Next**: Navigates to Flashing page with credentials

### 3. **Flashing Progress** (`flashing.html`)
- **Purpose**: Send credentials to ESP32 and show progress
- **Features**:
  - Animated progress bar
  - Status messages
- **Backend Integration**:
  - `POST /serial/connect` - Sends WiFi credentials to device
  - Payload: `{port, ssid, password, baud}`
- **Duration**: 3-4 seconds
- **Next**: Auto-navigates to Calibration

### 4. **Calibration Screen** (`calibration.html`)
- **Purpose**: 9-point eye tracking calibration
- **Features**:
  - Pre-calibration preview with "Enter Fullscreen" button
  - Fullscreen calibration grid (3x3 = 9 nodes)
  - Interactive node clicking system
  - Active node highlighting (green with pulse animation)
  - Completed nodes turn blue
  - Visual user cursor tracking
  - Frame 6 label during calibration
  - Completion modal when all 9 nodes clicked
- **Backend Integration**:
  - `POST /prefs/calibration` - Saves calibration data
  - Payload: `{calibration_data: [...], timestamp}`
  - Sets `has_onboarded: true`
- **Flow**:
  1. Click "Enter Fullscreen"
  2. Click each highlighted node in sequence (9 total)
  3. Completion modal appears (Frame 7)
  4. Click "Exit Fullscreen"
- **Next**: Navigates to Settings Menu

### 5. **Settings Menu** (`settings.html`)
- **Purpose**: Main settings and control panel
- **Features**:
  - Connection Mode toggle (WiFi/Wired)
  - Horizontal Sensitivity slider (0-100)
  - Vertical Sensitivity slider (0-100)
  - **Buttons**:
    - Recalibrate → Returns to calibration
    - Advanced Settings → Opens advanced settings
    - Live Info View → (Placeholder for live data view)
    - Flash WiFi Information → Returns to connection page
  - Device Info button (top right)
  - Frame indicator: "860 × 860, Frame 10"
- **Backend Integration**:
  - `GET /prefs` - Loads saved preferences
  - `PUT /prefs` - Saves settings changes
  - `GET /serial/status` - Device info display
- **Persistence**: Settings saved to both localStorage and backend

### 6. **Advanced Settings Menu** (`advanced-settings.html`)
- **Purpose**: Additional configuration options
- **Features**:
  - Preference 1 dropdown
  - Preference 2 dropdown
  - Horizontal Sensitivity slider (0-100)
  - Vertical Sensitivity slider (0-100)
  - Back button → Returns to Settings Menu
  - Device Info button (top right)
  - Frame indicator: "Frame 9"
- **Backend Integration**:
  - `GET /prefs` - Loads preferences
  - `PUT /prefs` - Saves preferences
- **Navigation**: Back button returns to Settings Menu

## Navigation Map

```
Welcome (2s auto)
    ↓
Connect Form
    ↓ (on submit)
Flashing Progress (3.5s)
    ↓
Calibration (pre-screen)
    ↓ (Enter Fullscreen)
Calibration (9-dot grid)
    ↓ (all nodes clicked)
Completion Modal
    ↓ (Exit Fullscreen)
Settings Menu
    ↓ (Advanced Settings button)
Advanced Settings
    ↓ (Back button)
Settings Menu
```

### Alternative Paths:
- Connect Form → "Proceed With Wired Connection" → Calibration
- Settings → "Recalibrate" → Calibration
- Settings → "Flash WiFi Information" → Connect Form
- Any page → "Device Info" button → Modal popup

## 🔧 Backend Integration

### API Endpoints Used:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/serial/ports` | GET | List available serial ports |
| `/serial/connect` | POST | Send WiFi credentials to ESP32 |
| `/serial/status` | GET | Get device connection status |
| `/prefs` | GET | Load user preferences |
| `/prefs` | PUT | Save user preferences |
| `/prefs/calibration` | POST | Save calibration data |
| `/health` | GET | Server health check |

### Data Persistence:

**Preferences stored (`~/.eyecue/prefs.json`):**
```json
{
  "has_onboarded": true,
  "wifi_ssid": "MyNetwork",
  "wifi_password": "***",
  "last_serial_port": "/dev/tty.usbserial",
  "connection_method": "wifi",
  "horizontal_sensitivity": 50,
  "vertical_sensitivity": 50,
  "preference_1": "default",
  "preference_2": "default",
  "calibration_data": [...],
  "calibration_timestamp": 1708021200000
}
```

## Visual Design

- **Color Scheme**:
  - Primary: Blue (#4285f4)
  - Success: Green (#4caf50, #34a853)
  - Warning: Orange (#ffa726)
  - Neutral: Gray (#999, #e0e0e0)

- **Interactive Elements**:
  - Buttons with hover effects and transitions
  - Sliders with custom styling
  - Animated progress bars
  - Pulsing active nodes during calibration

- **Responsive Design**:
  - Centered containers
  - Flexible layouts
  - 860×860 optimal size for settings screens

## Running the Application

### Start Backend:
```bash
cd /Users/williamzhang/Documents/GitHub/eyecue
./restart_server.sh
```
Server runs at: `http://127.0.0.1:5001`

### Start Electron App:
```bash
cd app/frontend
npm install  # First time only
npm start
```

### Development Mode:
```bash
npm run dev  # Opens with DevTools
```

## Testing the Flow

1. **Start the backend server**
2. **Launch Electron app**
3. **Follow the flow**:
   - Wait or click on Welcome screen
   - Fill in WiFi credentials (any test values work)
   - Select a serial port (or auto-detect)
   - Watch flashing animation
   - Enter fullscreen for calibration
   - Click all 9 nodes in sequence
   - Exit to settings
   - Test navigation between settings pages
   - Verify sliders and dropdowns save properly

## Debugging

### Check Backend Status:
```bash
curl http://127.0.0.1:5001/health
```

### View Preferences:
```bash
curl http://127.0.0.1:5001/prefs
```

### Check Serial Ports:
```bash
curl http://127.0.0.1:5001/serial/ports
```

### View Saved Preferences:
```bash
cat ~/.eyecue/prefs.json
```

## Notes

- **Fullscreen**: May not work in all environments; calibration still works in windowed mode
- **Serial Communication**: Requires actual ESP32 device; skips gracefully if not available
- **Persistence**: Uses both localStorage (frontend) and JSON file (backend) for redundancy
- **CORS**: Enabled for all routes to allow Electron → Flask communication
- **Development**: Flask runs with debug mode and auto-reload enabled

## Future Enhancements

- Implement Live Info View with real-time cursor tracking
- Add device firmware version checking
- Implement actual cursor control integration
- Add user profiles and multiple calibration saves
- Create proper modal dialogs instead of alerts
- Add error recovery and retry mechanisms
- Implement connection status indicators
- Add tooltips and help text
