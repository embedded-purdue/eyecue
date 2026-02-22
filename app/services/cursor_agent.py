"""Cursor agent that polls Flask for samples/params and applies cursor updates."""

from __future__ import annotations

import time
import threading
from typing import Any, Dict, Optional

import requests

from app.config import AGENT_STATS_INTERVAL_S, CURSOR_ENABLED, CURSOR_RATE_HZ, HTTP_TIMEOUT_S, INTERNAL_BASE_URL

try:
    import pyautogui
except Exception:  # pragma: no cover - optional runtime dependency
    pyautogui = None


class CursorAgent:
    def __init__(self, *, base_url: str = INTERNAL_BASE_URL, rate_hz: float = CURSOR_RATE_HZ) -> None:
        self._base_url = base_url.rstrip("/")
        self._rate_hz = max(1.0, rate_hz)

        self._session = requests.Session()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._errors_total = 0
        self._last_error: Optional[str] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="cursor-agent", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _get_json(self, path: str) -> Optional[Dict[str, Any]]:
        url = f"{self._base_url}{path}"
        response = self._session.get(url, timeout=HTTP_TIMEOUT_S)
        response.raise_for_status()
        payload = response.json()
        if payload.get("ok"):
            return payload.get("data")
        return None

    def _post_stats(self, *, connected: bool, loop_hz: float, queue_lag_ms: Optional[int]) -> None:
        payload = {
            "agent": "cursor",
            "ts_ms": int(time.time() * 1000),
            "connected": connected,
            "loop_hz": round(loop_hz, 2),
            "errors_total": self._errors_total,
            "last_error": self._last_error,
            "queue_lag_ms": queue_lag_ms,
        }
        try:
            self._session.post(
                f"{self._base_url}/internal/ingest/stats",
                json=payload,
                timeout=HTTP_TIMEOUT_S,
            )
        except Exception:
            pass

    def _apply_cursor(self, sample: Dict[str, Any], params: Dict[str, Any]) -> None:
        if not CURSOR_ENABLED or pyautogui is None:
            return

        x = float(sample.get("x", 0.0))
        y = float(sample.get("y", 0.0))

        h_sens = max(1, int(params.get("horizontal_sensitivity", 50))) / 50.0
        v_sens = max(1, int(params.get("vertical_sensitivity", 50))) / 50.0

        mode = params.get("cursor_mode", "abs")
        if mode == "rel":
            pyautogui.moveRel(x * h_sens, y * v_sens)
        else:
            pyautogui.moveTo(x * h_sens, y * v_sens)

    def _run(self) -> None:
        interval = 1.0 / self._rate_hz
        started = time.monotonic()
        loops = 0
        last_stats_at = time.monotonic()

        try:
            while not self._stop_event.is_set():
                tick = time.monotonic()
                loops += 1
                connected = False
                queue_lag_ms: Optional[int] = None

                try:
                    sample = self._get_json("/internal/cursor/latest")
                    params = self._get_json("/internal/cursor/params") or {}

                    if sample:
                        connected = True
                        ts_ms = int(sample.get("ts_ms", int(time.time() * 1000)))
                        queue_lag_ms = int(time.time() * 1000) - ts_ms
                        self._apply_cursor(sample, params)

                        report_payload = {
                            "agent": "cursor",
                            "ts_ms": int(time.time() * 1000),
                            "connected": connected,
                            "queue_lag_ms": queue_lag_ms,
                            "applied_sample": {
                                "seq": sample.get("seq"),
                                "x": sample.get("x"),
                                "y": sample.get("y"),
                                "source": sample.get("source"),
                            },
                        }
                        try:
                            self._session.post(
                                f"{self._base_url}/internal/ingest/stats",
                                json=report_payload,
                                timeout=HTTP_TIMEOUT_S,
                            )
                        except Exception:
                            pass
                except Exception as exc:
                    self._errors_total += 1
                    self._last_error = str(exc)

                now = time.monotonic()
                if (now - last_stats_at) >= AGENT_STATS_INTERVAL_S:
                    elapsed = max(0.001, now - started)
                    loop_hz = loops / elapsed
                    self._post_stats(connected=connected, loop_hz=loop_hz, queue_lag_ms=queue_lag_ms)
                    last_stats_at = now

                sleep_for = interval - (time.monotonic() - tick)
                if sleep_for > 0:
                    time.sleep(sleep_for)
        finally:
            now = time.monotonic()
            elapsed = max(0.001, now - started)
            loop_hz = loops / elapsed
            self._post_stats(connected=False, loop_hz=loop_hz, queue_lag_ms=None)
            self._session.close()
