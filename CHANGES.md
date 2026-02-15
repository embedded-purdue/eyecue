# EyeCue – Change Log

This document describes every file that was modified or created during the
OrloskyPupil integration and gaze-vector refactor.

---

## New files

### `eyeball_model.py`

**Purpose:** Accurate 3-D eyeball rotation-centre estimation and gaze vector
calculation using a sphere model.

**Why it was added:**
The original `extract_gaze_numbers` method mapped pixel offsets to gaze angles
with a simple linear formula:

```
offset = (pixel - roi_center) / roi_size   # linear
x_3d   = offset * 12mm                    # placed on sphere
```

This works reasonably near the centre of the screen but becomes increasingly
wrong at the edges because the true relationship is nonlinear (perspective
projection).  The error is typically 5–15° at screen corners.

**What it does:**

1. **Pinhole camera model** – converts every detected pupil pixel `(u, v)` into
   a 3-D unit ray using:
   ```
   d = normalize([(u - px) / f,  (v - py) / f,  1])
   ```
   where `px, py` is the principal point (image centre) and `f` is the
   effective focal length in pixels.

2. **Eye-sphere model** – the pupil is assumed to move on the surface of a
   sphere of radius `R = 12 mm` centred at the eyeball rotation centre `C`.
   For each camera ray the exact 3-D pupil position `P` is found by solving
   the ray–sphere intersection:
   ```
   t² − 2t(d·C) + |C|² − R² = 0
   P = t · d   (near intersection, front of eye)
   ```

3. **Running eyeball-centre estimate** – each new observation nudges `C` via an
   exponential moving average so the model adapts to where the eye actually
   sits in front of the camera:
   ```
   C_new = P + R · normalize(C_old − P)
   C     = (1 − α) · C + α · C_new
   ```
   `α = 0.15` for the first 40 frames (fast warm-up), then `α = 0.03`
   (stable tracking).

4. **Gaze vector** – `g = normalize(P − C)`.  When the eye looks straight into
   the camera `g = (0, 0, −1)` and both angles are 0°.

5. **Duplicate-call guard** – `update()` is idempotent for the same `(x, y)`
   pixel so calling `extract_gaze_numbers` twice per frame (once for metrics,
   once for display) does not corrupt the running estimate.

**Key tuning parameters** (constructor arguments):

| Parameter | Default | Meaning |
|---|---|---|
| `focal_length` | auto | Effective focal length in pixels |
| `zoom_factor` | `8.0` | Digital zoom applied before detection |
| `base_fov_deg` | `60.0` | Physical webcam horizontal FOV (°) |
| `eye_radius_mm` | `12.0` | Eye-sphere radius (mm) |
| `init_depth_mm` | `500.0` | Initial eye-to-camera distance guess (mm) |

To override defaults, pass custom values when the model is first created.
Edit the lazy-init block in `ContourGazeTracker.extract_gaze_numbers`.

---

## Modified files

### `pupil_detector.py`

**What changed:**

1. **Replaced entire detection algorithm** – the old contour-scoring approach
   (threshold → blur → OpenCV contours → score by darkness + circularity) was
   replaced with a single call to `OrloskyPupil.process_frame()`.

2. **Removed `roi_center` from the return value** – the old signature was
   `(pupil_center, roi_center, bbox)` where `roi_center` was always `None` and
   never used by any caller.  The new signature is `(pupil_center, bbox)`.

**Before:**
```python
def detect_pupil_contour(frame):
    # ...threshold, blur, contour scoring...
    return (full_cx, full_cy), (cx, cy), (w_box, h_box)
```

**After:**
```python
from OrloskyPupil import process_frame as orlosky_process_frame

def detect_pupil_contour(frame):
    rotated_rect = orlosky_process_frame(frame)
    center, axes, _angle = rotated_rect
    if center == (0, 0) and axes == (0, 0):
        return None, None
    return (int(center[0]), int(center[1])), (int(axes[0]), int(axes[1]))
```

**Why OrloskyPupil is better:**
It finds the darkest region first, applies three thresholds (strict / medium /
relaxed) simultaneously, dilates each binary image, finds contours, filters by
area and aspect ratio, then scores every candidate ellipse by how well the
detected contour pixels actually lie on the fitted ellipse.  The threshold
level that scores highest wins.  This is significantly more robust to eyelid
occlusion and lighting variation than a single fixed threshold.

---

### `contour_gaze_tracker.py`

**What changed:**

1. **Added import** for `EyeballModel`.

2. **Added `self.eyeball_model = None`** to `__init__` – the model is
   lazy-initialised on the first call to `extract_gaze_numbers` so the frame
   dimensions are available.

3. **Replaced `extract_gaze_numbers`** – the entire body was replaced.  The
   method now:
   - Lazy-inits `EyeballModel` on first call.
   - Calls `eyeball_model.update(pupil_center)` to refine the running
     eyeball-centre estimate.
   - Calls `eyeball_model.get_gaze_data(pupil_center)` and returns its dict.
   - The returned dict has the same keys as before (`single_gaze_vector`,
     `single_angles`, `single_offset`) plus two new debug keys
     (`eye_center_3d`, `tilt_deg`), so all existing callers continue to work.

4. **Removed `roi_center` parameter** from `extract_gaze_numbers` signature.

5. **Updated both call sites** in `run()` to drop the `roi_center` argument.

6. **Updated `detect_pupil_contour` unpack** from three values to two:
   ```python
   # before
   pupil_center, roi_center, bbox = detect_pupil_contour(frame)
   # after
   pupil_center, bbox = detect_pupil_contour(frame)
   ```

---

### `test_gaze_angles.py`

**What changed:**

1. **Updated `detect_pupil_contour` unpack** from three values to two.

2. **Removed `roi_center` argument** from the `extract_gaze_numbers` call.

No logic changes – the file works identically to before but now calls the
correct (cleaned-up) function signatures.

---

### `blink_detector.py`

**What changed:**

1. **Updated `detect_pupil_contour` unpack** from three values to two:
   ```python
   # before
   pupil_center, roi_center, bbox = detect_pupil_contour(frame)
   # after
   pupil_center, bbox = detect_pupil_contour(frame)
   ```

`roi_center` was captured but never read inside `detect_blink`, so this is a
pure cleanup with no behaviour change.

---

### `autoscroll.py`

**What changed:**

1. **Updated `detect_pupil_contour` unpack** from three values to two:
   ```python
   # before
   (full_cx, full_cy), _, _ = detect_pupil_contour(frame)
   # after
   (full_cx, full_cy), _ = detect_pupil_contour(frame)
   ```

---

## Files that were NOT changed

| File | Reason |
|---|---|
| `OrloskyPupil.py` | Source of the detection algorithm; used as-is |
| `CursorController.py` | Only receives gaze angles; no pupil detection |
| `metrics_collector.py` | No changes to the metrics interface |
| `main_module.py` | Uses the same public API; unaffected |
| `app/` | Flask web app; no eye-tracking logic |

---

## Data-flow summary

```
Camera frame
    │
    ▼
pupil_detector.detect_pupil_contour(frame)
    │  OrloskyPupil.process_frame()
    │    darkest region → 3-level threshold → contour filter → ellipse fit
    │
    ▼  returns (pupil_center, bbox)
    │
ContourGazeTracker.extract_gaze_numbers(pupil_center, frame_shape)
    │  EyeballModel.update(pupil_center)     ← refine sphere centre
    │  EyeballModel.get_gaze_data(pupil_center)
    │    pixel → camera ray (pinhole model)
    │    ray ∩ eye sphere → 3-D pupil position P
    │    gaze = normalize(P − C)
    │    angles: theta_h = atan2(g.x, −g.z)
    │            theta_v = atan2(−g.y, −g.z)
    │
    ▼  returns {single_gaze_vector, single_angles, single_offset, …}
    │
CursorController.update_target(theta_h, theta_v, gyro_h, gyro_v)
    │  applies head-rotation compensation
    │  projects gaze onto screen plane
    │
    ▼
pyautogui.moveTo(x, y)
```
