# eyecue

eyecue - eye-controlled cursor system for accessibility

## setup

Make sure you do not have Anaconda installed. Copy `.env.example` to a new `.env` file.
If you are simulating a webcam, set `BYPASS_SERIAL` to `true`.

Setup the virtual environment (venv) by running `python3 -m venv env` from the project root.
Then, install all dependencies by running `pip install -r requirements.txt`.

Resolve frontend dependencies and run the desktop app from Electron:

```bash
cd app/frontend
npm install
npm run start:desktop
```

`start:desktop` starts Electron immediately and runs the live Python backend in development.
Use `npm run start:desktop:binary` when you explicitly want the PyInstaller backend path.

This will launch the eyecue app. To build the app, see the instructions below.

Open the app and run `xattr -cr /path/to/eyecue-frontend.app` to remove the quarantine.
Run `./build.sh` from the repo root (or `npm run make` in `app/frontend`) to create a desktop binary in `app/frontend/out/make/`.

## overview

real-time pupil detection and gaze tracking system using computer vision. designed for eye-controlled cursor movement and accessibility applications.

## features

- **pupil detection**: multi-criteria contour-based detection with filtering
- **gaze tracking**: 3d gaze vectors and angle calculation
- **esp32 camera support**: works with esp32-cam, webcam, or video files
- **performance metrics**: real-time fps, detection rate, position stability tracking
- **video export**: record tracking sessions with overlays

## quick start

### basic usage

```bash
# webcam
python3 contour_gaze_tracker.py --camera 0

# esp32 camera
python3 contour_gaze_tracker.py --camera http://192.168.4.49/stream

# record video
python3 contour_gaze_tracker.py --camera 0 --output test.mp4

# desktop app (recommended)
cd app/frontend && npm run start:desktop

# backend-only fallback (development diagnostics)
python3 -m app.app
```

Desktop app entrypoint (recommended):

```bash
cd app/frontend
npm run start:desktop
```

### command line arguments

- `--camera`: camera index (0, 1, 2...), video file path, or esp32 stream url
- `--output`: save video file (e.g., `output.mp4`)
- `--no-metrics`: disable metrics collection
- `--metrics-interval N`: auto-save metrics every n frames (default: 100)

### keyboard controls

- `q` - quit and save metrics
- `s` - save metrics immediately

## project structure

### core modules

- `contour_gaze_tracker.py` - main gaze tracking script
- `pupil_detector.py` - pupil detection algorithm
- `metrics_collector.py` - performance metrics tracking
- `CursorController.py` - cursor movement control (for integration)

### utilities

- `run_esp32_gaze.sh` - quick script to run with esp32 camera
- `blink_detector.py` - blink detection for click functionality
- `autoscroll.py` - auto-scroll functionality

For the desktop product, scripts above are optional/legacy helpers; Electron is the main entrypoint.

### archived

- `old_files/` - previous implementations and experimental code

## algorithm details

### pupil detection

uses contour analysis with multi-criteria filtering:

- gaussian blur for noise reduction
- adaptive threshold based on mean intensity
- morphological operations to clean up
- size filtering (rejects noise and iris)
- aspect ratio filtering (rejects eyelashes)
- darkness and circularity checks
- scoring system to select best candidate

### gaze calculation

- calculates 3d gaze vectors from pupil position
- converts to horizontal/vertical angles
- uses exponential smoothing for stable tracking

### metrics

tracks in real-time:

- detection rate (successful detections / total frames)
- fps (frames per second)
- position jitter (frame-to-frame stability)
- position variance (overall consistency)
- detection latency

metrics saved automatically to json/csv on exit.

## current status

- ✅ pupil detection working with esp32 camera
- ✅ gaze angle calculation
- ✅ metrics collection system
- ✅ video export functionality
- ✅ cursor control integration
- ⏳ blink detection for clicking (next step)

## demo videos

test videos available in `test_vid/` directory.
