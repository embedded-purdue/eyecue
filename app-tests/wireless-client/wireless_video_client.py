#!/usr/bin/env python3
"""Wireless client emulator for EyeCue Flask ingest endpoints.

Replays frames from a local video and uploads them to:
- /ingest/wireless/frame
- /ingest/wireless/stats
Optionally also posts /ingest/wireless/cursor for debugging.
"""

from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path
from typing import Optional

import requests

try:
    import cv2
except ModuleNotFoundError as exc:  # pragma: no cover - runtime dependency
    raise SystemExit(
        "OpenCV is required for wireless_video_client.py. "
        "Install opencv-python or opencv-python-headless."
    ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wireless video test client for EyeCue")
    parser.add_argument("--base-url", default="http://127.0.0.1:5051", help="Flask base URL")
    parser.add_argument("--video-path", required=True, help="Path to local video file")
    parser.add_argument("--fps", type=float, default=15.0, help="Upload FPS (default: 15)")
    parser.add_argument("--device-id", default="wireless-test-client", help="Device ID label")
    parser.add_argument("--jpeg-quality", type=int, default=80, help="JPEG quality 1-100")
    parser.add_argument("--stats-interval-sec", type=float, default=2.0, help="Stats post interval")
    parser.add_argument("--cursor-override", action="store_true", help="Also send synthetic cursor samples")
    parser.add_argument("--loop", action="store_true", help="Loop video playback")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames (0 = unlimited)")
    return parser.parse_args()


def post_stats(
    session: requests.Session,
    base_url: str,
    *,
    device_id: str,
    frames_sent: int,
    frames_failed: int,
    last_error: Optional[str],
) -> None:
    payload = {
        "agent": "wireless",
        "connected": True,
        "device_id": device_id,
        "frames_sent": frames_sent,
        "frames_failed": frames_failed,
        "last_error": last_error,
        "ts_ms": int(time.time() * 1000),
    }
    try:
        session.post(f"{base_url}/ingest/wireless/stats", json=payload, timeout=2.0)
    except Exception:
        pass


def post_cursor_override(
    session: requests.Session,
    base_url: str,
    *,
    device_id: str,
    frame_index: int,
) -> None:
    x = 960 + int(200 * math.sin(frame_index / 15.0))
    y = 540 + int(120 * math.cos(frame_index / 20.0))
    payload = {
        "x": x,
        "y": y,
        "source": "wireless",
        "device_id": device_id,
        "ts_ms": int(time.time() * 1000),
        "confidence": 0.5,
    }
    try:
        session.post(f"{base_url}/ingest/wireless/cursor", json=payload, timeout=2.0)
    except Exception:
        pass


def open_capture(video_path: Path):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video file: {video_path}")
    return cap


def main() -> int:
    args = parse_args()

    video_path = Path(args.video_path)
    if not video_path.exists():
        print(f"Video not found: {video_path}")
        return 2

    base_url = args.base_url.rstrip("/")
    frame_interval = 1.0 / max(0.1, args.fps)
    jpeg_quality = max(1, min(100, int(args.jpeg_quality)))

    session = requests.Session()
    cap = open_capture(video_path)

    frames_sent = 0
    frames_failed = 0
    frame_index = 0
    last_error: Optional[str] = None
    started = time.monotonic()
    last_stats = started

    print(f"Streaming {video_path} to {base_url} at {args.fps:.2f} FPS")

    try:
        while True:
            tick = time.monotonic()
            ok, frame = cap.read()

            if not ok:
                if args.loop:
                    cap.release()
                    cap = open_capture(video_path)
                    continue
                break

            encode_ok, jpg = cv2.imencode(
                ".jpg",
                frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality],
            )
            if not encode_ok:
                frames_failed += 1
                last_error = "JPEG encoding failed"
                continue

            frame_ts_ms = int(time.time() * 1000)
            files = {
                "frame": (f"frame_{frame_index:06d}.jpg", jpg.tobytes(), "image/jpeg"),
            }
            form = {
                "device_id": args.device_id,
                "frame_ts_ms": str(frame_ts_ms),
                "seq": str(frame_index),
                "width": str(frame.shape[1]),
                "height": str(frame.shape[0]),
                "format": "jpeg",
                "source_tag": "wireless-video-client",
            }

            try:
                response = session.post(
                    f"{base_url}/ingest/wireless/frame",
                    files=files,
                    data=form,
                    timeout=3.0,
                )
                if response.status_code == 200:
                    frames_sent += 1
                else:
                    frames_failed += 1
                    try:
                        err_payload = response.json()
                        last_error = err_payload.get("error") or f"HTTP {response.status_code}"
                    except Exception:
                        last_error = f"HTTP {response.status_code}"
            except Exception as exc:
                frames_failed += 1
                last_error = str(exc)

            if args.cursor_override:
                post_cursor_override(
                    session,
                    base_url,
                    device_id=args.device_id,
                    frame_index=frame_index,
                )

            now = time.monotonic()
            if (now - last_stats) >= max(0.2, args.stats_interval_sec):
                post_stats(
                    session,
                    base_url,
                    device_id=args.device_id,
                    frames_sent=frames_sent,
                    frames_failed=frames_failed,
                    last_error=last_error,
                )
                elapsed = max(0.001, now - started)
                eff_fps = frames_sent / elapsed
                print(
                    f"sent={frames_sent} failed={frames_failed} eff_fps={eff_fps:.2f} "
                    f"last_error={last_error or 'none'}"
                )
                last_stats = now

            frame_index += 1
            if args.max_frames > 0 and frame_index >= args.max_frames:
                break

            sleep_for = frame_interval - (time.monotonic() - tick)
            if sleep_for > 0:
                time.sleep(sleep_for)

        post_stats(
            session,
            base_url,
            device_id=args.device_id,
            frames_sent=frames_sent,
            frames_failed=frames_failed,
            last_error=last_error,
        )

        total_elapsed = max(0.001, time.monotonic() - started)
        print(
            f"Completed: sent={frames_sent} failed={frames_failed} "
            f"duration={total_elapsed:.2f}s avg_fps={frames_sent / total_elapsed:.2f}"
        )
        return 0
    finally:
        cap.release()
        session.close()


if __name__ == "__main__":
    sys.exit(main())
