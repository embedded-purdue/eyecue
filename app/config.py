"""Application configuration for EyeCue desktop runtime."""

from __future__ import annotations

import os


FLASK_HOST = os.getenv("EYE_FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("EYE_FLASK_PORT", "5001"))

INTERNAL_BASE_URL = os.getenv("EYE_INTERNAL_BASE_URL", f"http://{FLASK_HOST}:{FLASK_PORT}")

CURSOR_RATE_HZ = float(os.getenv("EYE_CURSOR_RATE_HZ", "30"))
SOURCE_STALE_MS = int(os.getenv("EYE_SOURCE_STALE_MS", "2000"))
AGENT_STATS_INTERVAL_S = float(os.getenv("EYE_AGENT_STATS_INTERVAL_S", "1.0"))
HTTP_TIMEOUT_S = float(os.getenv("EYE_AGENT_HTTP_TIMEOUT_S", "0.5"))

ALLOWED_RUNTIME_MODES = {"serial", "wired", "wifi"}


def env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


CURSOR_ENABLED = env_flag("EYE_ENABLE_CURSOR", default=False)
