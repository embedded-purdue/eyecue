# Wireless Video Test Client

This client emulates an ESP32 wireless sender by replaying a local video file and posting frames to the Flask backend.

## Endpoint usage

- `POST /ingest/wireless/frame` (multipart JPEG upload)
- `POST /ingest/wireless/stats` (periodic device stats)
- Optional: `POST /ingest/wireless/cursor` (cursor override/debug)

## Requirements

- Python deps from project root `requirements.txt`
- OpenCV for video replay:

```bash
pip install opencv-python
```

or headless:

```bash
pip install opencv-python-headless
```

## Run

From repo root:

```bash
python3 app-tests/wireless-client/wireless_video_client.py \
  --video-path test_vid/<your_video_file> \
  --base-url http://127.0.0.1:5051
```

## Useful options

- `--fps 15`
- `--device-id wireless-test-client`
- `--jpeg-quality 80`
- `--stats-interval-sec 2`
- `--cursor-override`
- `--loop`
- `--max-frames 300`

## Example

```bash
python3 app-tests/wireless-client/wireless_video_client.py \
  --video-path test_vid/demo.mp4 \
  --fps 20 \
  --cursor-override \
  --max-frames 500
```

Then verify backend state:

```bash
curl http://127.0.0.1:5051/runtime/state
```

Look for `wireless_video.frames_received` increasing.
