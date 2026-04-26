"""Minimal application configuration for EyeCue desktop runtime."""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional local dev dependency
    def load_dotenv(*_args, **_kwargs):
        return False

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

FLASK_HOST = os.getenv("EYE_FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("EYE_FLASK_PORT", "5051"))
BYPASS_SERIAL = os.getenv("BYPASS_SERIAL", "false").lower() == "true"
SERIAL_DEBUG = os.getenv("EYE_SERIAL_DEBUG", "true").lower() == "true"

SERIAL_HANDSHAKE_ATTEMPTS = int(os.getenv("EYE_SERIAL_HANDSHAKE_ATTEMPTS", "3"))
# Phase 1: quick retries waiting for ACK WIFI_CONFIG <nonce>
SERIAL_ACK_RETRIES = int(os.getenv("EYE_SERIAL_ACK_RETRIES", "3"))
SERIAL_ACK_TIMEOUT_S = float(os.getenv("EYE_SERIAL_ACK_TIMEOUT_S", "1.5"))
# Phase 2: after ACK is confirmed, wait for OK <ip> or ERR ...
SERIAL_HANDSHAKE_ATTEMPT_TIMEOUT_S = float(os.getenv("EYE_SERIAL_HANDSHAKE_ATTEMPT_TIMEOUT_S", "6.0"))
STREAM_RETRY_DELAY_S = float(os.getenv("EYE_STREAM_RETRY_DELAY_S", "2.0"))

EYE_BASELINE_SAMPLES = int(os.getenv("EYE_BASELINE_SAMPLES", "30"))
EYE_BASELINE_DEADZONE_X = float(os.getenv("EYE_BASELINE_DEADZONE_X", "0.012"))
EYE_BASELINE_DEADZONE_Y = float(os.getenv("EYE_BASELINE_DEADZONE_Y", "0.016"))
EYE_BASELINE_GAIN_X = float(os.getenv("EYE_BASELINE_GAIN_X", "3.0"))
EYE_BASELINE_GAIN_Y = float(os.getenv("EYE_BASELINE_GAIN_Y", "3.4"))
EYE_BASELINE_CONFIDENCE_FLOOR = float(os.getenv("EYE_BASELINE_CONFIDENCE_FLOOR", "0.30"))

MJPEG_PATH_CANDIDATES = tuple(
    part.strip()
    for part in os.getenv("EYE_MJPEG_PATHS", ":81/stream")
    .split(",")
    if part.strip()
)
