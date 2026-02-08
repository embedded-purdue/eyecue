# EyeCue Electron Frontend

A basic Electron app that provides the setup sequence for the EyeCue eye-tracking device.

## Setup Sequence

1. **Welcome Screen** - Initial welcome with device connection prompt
2. **Connection Form** - WiFi credentials and serial port selection
3. **Flashing Progress** - Network information being sent to device
4. **Calibration** - First-time calibration setup with fullscreen option

## Installation

```bash
cd app/frontend
npm install
```

## Running the App

```bash
npm start
```

For development with DevTools:
```bash
npm run dev
```

## Project Structure

```
app/frontend/
├── main.js              # Electron main process
├── preload.js           # Preload script (security bridge)
├── package.json         # Dependencies and scripts
├── pages/              
│   ├── welcome.html     # Welcome screen
│   ├── connect.html     # Connection form
│   ├── flashing.html    # Progress indicator
│   └── calibration.html # Calibration setup
├── scripts/            
│   ├── welcome.js       # Welcome screen logic
│   ├── connect.js       # Form submission logic
│   ├── flashing.js      # Progress logic
│   └── calibration.js   # Calibration logic
└── styles/
    └── main.css         # Application styles
```

## Next Steps

- Integrate with Flask backend (`/serial/connect` and `/serial/status` endpoints)
- Add serial port auto-detection
- Implement actual calibration routine
- Add error handling and validation
- Create device info modal
