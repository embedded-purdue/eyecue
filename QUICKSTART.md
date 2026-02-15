# EyeCue - Quick Start Guide

## 🚀 Start the Application

### Terminal 1: Start Backend Server
```bash
cd /Users/williamzhang/Documents/GitHub/eyecue
./restart_server.sh
```

Expected output:
```
Restarting Flask server...
Previous server stopped.
Starting new server...
Server restarted!
📡 Access at: http://127.0.0.1:5001
```

### Terminal 2: Start Electron App
```bash
cd /Users/williamzhang/Documents/GitHub/eyecue/app/frontend
npm start
```

The Electron window will open automatically showing the Welcome screen.

## 📱 Complete User Journey

### 1️⃣ Welcome Screen (Auto-advances)
- Shows EyeCue logo and "Connect device with provided cable"
- Automatically moves to next screen after 2 seconds

### 2️⃣ Connection Form
- Enter WiFi Network Name
- Enter WiFi Password
- Select Serial Port (will auto-populate available ports)
- Click "Connect" button
- OR click "Proceed With Wired Connection" to skip WiFi setup

### 3️⃣ Flashing Progress
- Animated progress bar
- Shows "Flashing Network Information..."
- Connects to backend: `POST /serial/connect`
- Auto-advances after successful connection

### 4️⃣ Calibration - Pre Screen
- Preview showing cursor indicator
- Click "Enter Fullscreen" to begin calibration

### 5️⃣ Calibration - 9-Dot Grid
- **Frame 6** - Active calibration
- Click each highlighted GREEN node (9 total)
- Nodes turn BLUE when completed
- Instructions at bottom explain current node
- **Frame 7** - All nodes completed, shows completion modal

### 6️⃣ Completion Modal
- "Calibration Complete" message
- Click "Exit Fullscreen" to proceed

### 7️⃣ Settings Menu (Frame 10)
- **Connection Mode**: Toggle between WiFi/Wired
- **Horizontal Sensitivity**: Adjust with slider (0-100)
- **Vertical Sensitivity**: Adjust with slider (0-100)
- **Buttons**:
  - "Recalibrate" - Go back to calibration
  - "Advanced Settings" - Open Frame 9
  - "Live Info View" - (Coming soon)
  - "Flash WiFi Information" - Return to connection form
- **Device Info** button (top right) - View connection status

### 8️⃣ Advanced Settings (Frame 9)
- **Preference 1** & **Preference 2** dropdowns
- **Horizontal/Vertical Sensitivity** sliders
- **Back** button - Return to Settings Menu
- **Device Info** button (top right)

## 🔄 Navigation Flow

```
Welcome → Connect → Flashing → Calibration → Settings ⟷ Advanced Settings
            ↑                        ↑           ↓
            └────────────────────────┴───────────┘
         (Flash WiFi)           (Recalibrate)
```

## 🧪 Testing Checklist

- [ ] Backend server starts successfully
- [ ] Electron app launches
- [ ] Welcome screen auto-advances
- [ ] Serial ports populate in dropdown
- [ ] Connection form submits
- [ ] Flashing animation plays
- [ ] Calibration enters fullscreen
- [ ] All 9 nodes can be clicked
- [ ] Completion modal appears
- [ ] Settings page loads with saved values
- [ ] Sensitivity sliders update in real-time
- [ ] Advanced settings opens and returns
- [ ] Device info shows current status
- [ ] Navigation between all pages works

## 🐛 Troubleshooting

### Backend Not Starting
```bash
# Check if port 5001 is in use
lsof -i:5001

# Kill process if needed
lsof -ti:5001 | xargs kill -9

# Restart server
./restart_server.sh
```

### Electron App Won't Start
```bash
cd app/frontend
rm -rf node_modules package-lock.json
npm install
npm start
```

### No Serial Ports Showing
- Make sure ESP32 device is connected via USB
- Check if drivers are installed for your device
- Try selecting "Auto-detect" option

### Settings Not Saving
- Check backend is running: `curl http://127.0.0.1:5001/health`
- Check preferences file: `cat ~/.eyecue/prefs.json`
- Check browser console (DevTools) for errors

### Fullscreen Not Working
- This is normal on some systems
- Calibration still works in windowed mode
- Click nodes as usual

## 📊 Backend API Quick Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Check if server is running |
| `/serial/ports` | GET | List available serial ports |
| `/serial/connect` | POST | Send WiFi credentials to device |
| `/serial/status` | GET | Get device connection status |
| `/prefs` | GET | Load user preferences |
| `/prefs` | PUT | Save user preferences |
| `/prefs/calibration` | POST | Save calibration data |

## 🎯 What's Working

✅ Full navigation flow from welcome to settings  
✅ Backend integration with Flask API  
✅ Serial port detection and listing  
✅ WiFi credential submission  
✅ 9-point calibration system with click tracking  
✅ Settings persistence (localStorage + backend)  
✅ Connection mode switching (WiFi/Wired)  
✅ Sensitivity adjustments  
✅ Device info display  
✅ Navigation between all pages  
✅ Calibration data storage  
✅ Preferences synchronization  

## 📂 Project Structure

```
eyecue/
├── run_server.py              # Flask backend entry point
├── restart_server.sh          # Quick server restart script
├── server_control.html        # Web-based server control
├── app/
│   ├── prefs.py              # Preferences storage
│   ├── serial_connect.py     # Serial communication
│   ├── routes/
│   │   ├── serial.py         # Serial API endpoints
│   │   ├── cursor.py         # Cursor control endpoints
│   │   └── prefs.py          # Preferences endpoints
│   ├── services/
│   │   └── serial_manager.py # Serial connection manager
│   └── frontend/
│       ├── main.js           # Electron main process
│       ├── preload.js        # Electron preload script
│       ├── package.json      # Dependencies
│       ├── pages/            # HTML pages
│       │   ├── welcome.html
│       │   ├── connect.html
│       │   ├── flashing.html
│       │   ├── calibration.html
│       │   ├── settings.html
│       │   └── advanced-settings.html
│       ├── scripts/          # Page logic
│       │   ├── welcome.js
│       │   ├── connect.js
│       │   ├── flashing.js
│       │   ├── calibration.js
│       │   ├── settings.js
│       │   └── advanced-settings.js
│       └── styles/
│           └── main.css      # All styles
```

## 🎓 Key Features Implemented

1. **Complete Setup Flow**: Welcome → Connect → Flash → Calibrate → Settings
2. **9-Dot Calibration**: Interactive clicking system with visual feedback
3. **Settings Persistence**: Saves to both localStorage and backend JSON
4. **Serial Integration**: Lists ports, connects to ESP32, sends WiFi credentials
5. **Navigation**: Free movement between all pages with proper back buttons
6. **Device Info**: Real-time status of connection and configuration
7. **Responsive UI**: Clean design matching provided mockups

## 🔧 Development Commands

```bash
# Start backend with auto-reload
cd /Users/williamzhang/Documents/GitHub/eyecue
./restart_server.sh

# Start Electron in dev mode (with DevTools)
cd app/frontend
npm run dev

# View backend logs
# (logs appear in terminal where restart_server.sh was run)

# Test API endpoints
curl http://127.0.0.1:5001/health
curl http://127.0.0.1:5001/serial/ports
curl http://127.0.0.1:5001/prefs

# View saved preferences
cat ~/.eyecue/prefs.json
```

---

**Ready to test!** Start both the backend and frontend, then walk through the complete flow. 🎉
