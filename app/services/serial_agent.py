"""Serial agent thread that forwards serial samples/stats to Flask via HTTP."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Dict, Optional

import requests

from app import serial_connect
from app.config import AGENT_STATS_INTERVAL_S, HTTP_TIMEOUT_S, INTERNAL_BASE_URL


class SerialAgent:
    def __init__(
        self,
        *,
        port: str,
        ssid: Optional[str],
        password: Optional[str],
        baud: int,
        mode: str,
        base_url: str = INTERNAL_BASE_URL,
    ) -> None:
        self._port = port
        self._ssid = ssid
        self._password = password
        self._baud = baud
        self._mode = mode
        self._base_url = base_url.rstrip("/")

        self._session = requests.Session()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._errors_total = 0
        self._last_error: Optional[str] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="serial-agent", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _post(self, path: str, payload: Dict[str, Any]) -> None:
        url = f"{self._base_url}{path}"
        self._session.post(url, json=payload, timeout=HTTP_TIMEOUT_S)

    def _post_stats(self, *, connected: bool, loop_hz: float, queue_lag_ms: Optional[int] = None) -> None:
        payload: Dict[str, Any] = {
            "agent": "serial",
            "ts_ms": int(time.time() * 1000),
            "connected": connected,
            "loop_hz": round(loop_hz, 2),
            "errors_total": self._errors_total,
            "last_error": self._last_error,
            "queue_lag_ms": queue_lag_ms,
            "port": self._port,
            "baud": self._baud,
            "mode": self._mode,
        }
        try:
            self._post("/internal/ingest/stats", payload)
        except Exception:
            pass

    def _run(self) -> None:
        ser = None
        lines_count = 0
        stats_started = time.monotonic()
        last_stats_at = time.monotonic()

        try:
            ser = serial_connect.open_serial(self._port, baud=self._baud)

            if self._ssid and self._password:
                serial_connect.send_wifi_credentials(ser, self._ssid, self._password)

            self._post_stats(connected=True, loop_hz=0.0)

            while not self._stop_event.is_set():
                try:
                    raw = ser.readline()
                except Exception as exc:
                    self._errors_total += 1
                    self._last_error = str(exc)
                    break

                now = time.monotonic()
                lines_count += 1

                if raw:
                    line = raw.decode("utf-8", errors="replace").strip()
                    if line:
                        try:
                            data = json.loads(line)
                        except json.JSONDecodeError:
                            data = None

                        if isinstance(data, dict) and "x" in data and "y" in data:
                            payload = {
                                "ts_ms": int(time.time() * 1000),
                                "x": data.get("x"),
                                "y": data.get("y"),
                                "confidence": data.get("confidence"),
                                "raw": data,
                                "source": "serial",
                            }
                            try:
                                self._post("/internal/ingest/cursor", payload)
                            except Exception as exc:
                                self._errors_total += 1
                                self._last_error = str(exc)
                        elif isinstance(data, dict):
                            stats_payload = {
                                "agent": "serial",
                                "ts_ms": int(time.time() * 1000),
                                "connected": True,
                                "errors_total": self._errors_total,
                                "last_error": self._last_error,
                                "raw": data,
                                "port": self._port,
                                "baud": self._baud,
                            }
                            try:
                                self._post("/internal/ingest/stats", stats_payload)
                            except Exception:
                                pass
                        elif "error" in line.lower():
                            self._last_error = line

                if (now - last_stats_at) >= AGENT_STATS_INTERVAL_S:
                    elapsed = max(0.001, now - stats_started)
                    loop_hz = lines_count / elapsed
                    self._post_stats(connected=True, loop_hz=loop_hz)
                    last_stats_at = now

        except Exception as exc:
            self._errors_total += 1
            self._last_error = str(exc)
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

            now = time.monotonic()
            elapsed = max(0.001, now - stats_started)
            loop_hz = lines_count / elapsed
            self._post_stats(connected=False, loop_hz=loop_hz)
            self._session.close()
