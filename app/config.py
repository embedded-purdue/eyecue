"""Minimal application configuration for EyeCue desktop runtime."""

from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

FLASK_HOST = os.getenv("EYE_FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("EYE_FLASK_PORT", "5051"))
BYPASS_SERIAL = os.getenv("BYPASS_SERIAL", "false").lower() == "true"

SERIAL_ACK_TIMEOUT_S = float(os.getenv("EYE_SERIAL_ACK_TIMEOUT_S", "20.0"))
STREAM_RETRY_DELAY_S = float(os.getenv("EYE_STREAM_RETRY_DELAY_S", "2.0"))

MJPEG_PATH_CANDIDATES = tuple(
    part.strip()
    for part in os.getenv("EYE_MJPEG_PATHS", "/stream,/mjpeg,/cam.mjpeg,/video")
    .split(",")
    if part.strip()
)
