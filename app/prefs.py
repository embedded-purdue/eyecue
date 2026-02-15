"""
Simple JSON preferences store shared between Electron and Flask.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict


DEFAULT_PREFS: Dict[str, Any] = {
    "has_onboarded": False,
    "wifi_ssid": "",
    "wifi_password": "",
    "last_serial_port": "",
    "connection_method": "",
}

_LOCK = threading.Lock()


def get_prefs_path() -> str:
    override = os.getenv("EYE_PREFS_PATH")
    if override:
        return override
    home = os.path.expanduser("~")
    return os.path.join(home, ".eyecue", "prefs.json")


def load_prefs() -> Dict[str, Any]:
    path = get_prefs_path()
    with _LOCK:
        if not os.path.exists(path):
            return dict(DEFAULT_PREFS)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return dict(DEFAULT_PREFS)

    merged = dict(DEFAULT_PREFS)
    if isinstance(data, dict):
        merged.update(data)
    return merged


def save_prefs(prefs: Dict[str, Any]) -> None:
    path = get_prefs_path()
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
    with _LOCK:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2, sort_keys=True)
