# EyeCue Flask Server

Backend API server for the EyeCue eye-tracking system.

## Quick Start

### 1. Install Dependencies

The virtual environment is already configured. Dependencies are installed.

```bash
# If you need to reinstall:
.venv/bin/pip install flask pyserial pyautogui numpy
```

### 2. Start the Server

The server runs on **port 5001** (port 5000 is used by macOS Control Center).

```bash
# Start server in background
.venv/bin/python run_server.py &
```

### 3. Check Server Status

```bash
curl http://127.0.0.1:5001/health
```

Expected response:
```json
{"status": "ok"}
```

## Server Control

### Option 1: Restart Script (Recommended)

```bash
./restart_server.sh
```

This script will:
- Kill any existing Flask server
- Start a fresh server instance
- Report the server URL

### Option 2: Control Panel (Web UI)

Open `server_control.html` in your browser for a visual control panel:

```bash
open server_control.html
```

Features:
- Real-time server status monitoring
- Check health endpoint
- View activity logs
- Restart instructions

### Option 3: Manual Control

**Stop server:**
```bash
pkill -f "python.*run_server.py"
```

**Start server:**
```bash
.venv/bin/python run_server.py &
```

**Check what's running on port 5001:**
```bash
lsof -i:5001
```

## API Endpoints

### Core Routes

- `GET /` - API info
- `GET /health` - Health check

### Serial Connection Routes

- `POST /serial/connect` - Send WiFi credentials to ESP32
  - Form params: `ssid`, `password`
- `GET /serial/status` - Get serial connection status

### Cursor Control Routes

- `POST /cursor/update` - Update cursor position
  - Form params: `xPos`, `yPos`

## Project Structure

```
eyecue/
├── run_server.py           # Main server entry point
├── restart_server.sh       # Quick restart script
├── server_control.html     # Web-based control panel
├── app/
│   ├── app.py             # Original Flask app
│   ├── serial_connect.py  # Serial communication module
│   └── routes/
│       ├── serial.py      # Serial API routes
│       └── cursor.py      # Cursor control routes
└── .venv/                 # Python virtual environment
```

## Development

### Debug Mode

The server runs with Flask's debug mode enabled by default, which provides:
- Auto-reload on code changes
- Detailed error pages
- Interactive debugger

### Logging

Server output is displayed in the terminal. To view logs:

```bash
# If running in background, check process
ps aux | grep run_server.py

# View logs (if redirected to file)
tail -f server.log
```

## Troubleshooting

### Port Already in Use

If you see "Address already in use":

```bash
# Kill process on port 5001
lsof -ti:5001 | xargs kill -9

# Or use the restart script
./restart_server.sh
```

### Import Errors

Make sure you're using the virtual environment Python:

```bash
which python  # Should show .venv/bin/python
.venv/bin/python run_server.py
```

### Module Not Found

Install missing packages:

```bash
.venv/bin/pip install <package-name>
```

## Security Notes

⚠️ **This is a development server** - Do not use in production!

For production deployment:
- Use a production WSGI server (gunicorn, uwsgi)
- Disable debug mode
- Add proper authentication
- Use HTTPS
- Configure CORS properly

## Integration with Electron Frontend

The Electron app in `app/frontend/` can make API calls to this server:

```javascript
// Example: Connect to WiFi
const response = await fetch('http://127.0.0.1:5001/serial/connect', {
  method: 'POST',
  headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  body: new URLSearchParams({ 
    ssid: 'MyNetwork', 
    password: 'password123' 
  })
});
```

See `app/frontend/scripts/connect.js` for implementation examples.
