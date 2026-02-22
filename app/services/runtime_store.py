"""Thread-safe runtime state store shared by routes and agents."""

from __future__ import annotations

import copy
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

from app.config import SOURCE_STALE_MS


def now_ms() -> int:
    return int(time.time() * 1000)


class RuntimeStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._seq = 0
        self._last_samples: Dict[str, Optional[Dict[str, Any]]] = {
            "serial": None,
            "wireless": None,
            "api": None,
        }
        self._sample_times: Dict[str, Deque[int]] = {
            "serial": deque(maxlen=90),
            "wireless": deque(maxlen=90),
            "api": deque(maxlen=90),
        }
        self._state: Dict[str, Any] = {
            "mode": "idle",
            "active_source": None,
            "connected": False,
            "serial": {
                "connected": False,
                "port": None,
                "baud": None,
                "last_error": None,
                "updated_at": None,
            },
            "wireless": {
                "connected": False,
                "device_id": None,
                "last_error": None,
                "updated_at": None,
            },
            "cursor": {
                "last_sample": None,
                "last_applied": None,
                "sample_rate_hz": 0.0,
                "queue_lag_ms": None,
                "last_error": None,
                "updated_at": None,
            },
            "agent_stats": {
                "serial": {},
                "cursor": {},
                "wireless": {},
            },
            "calibration": {
                "state": "idle",
                "session": None,
            },
            "last_error": None,
            "events": [],
        }

    def _record_event_locked(self, message: str) -> None:
        event = {"ts_ms": now_ms(), "message": message}
        events = self._state["events"]
        events.append(event)
        if len(events) > 100:
            del events[:-100]

    def _next_seq_locked(self) -> int:
        self._seq += 1
        return self._seq

    def _sample_is_fresh_locked(self, sample: Optional[Dict[str, Any]]) -> bool:
        if not sample:
            return False
        ts = sample.get("ts_ms")
        if ts is None:
            return False
        return (now_ms() - int(ts)) <= SOURCE_STALE_MS

    def _preferred_source_locked(self) -> Optional[str]:
        mode = self._state["mode"]
        if mode == "wifi":
            return "wireless"
        if mode in {"serial", "wired"}:
            return "serial"
        return None

    def _update_connected_locked(self) -> None:
        self._state["connected"] = bool(
            self._state["serial"]["connected"] or self._state["wireless"]["connected"]
        )

    def _fallback_active_source_locked(self) -> None:
        preferred = self._preferred_source_locked()
        active = self._state["active_source"]

        if active is None and preferred and self._sample_is_fresh_locked(self._last_samples.get(preferred)):
            self._state["active_source"] = preferred
            active = preferred

        if active is None:
            for candidate in (preferred, "serial", "wireless", "api"):
                if candidate and self._sample_is_fresh_locked(self._last_samples.get(candidate)):
                    self._state["active_source"] = candidate
                    active = candidate
                    break

        if not active:
            return

        active_sample = self._last_samples.get(active)
        if self._sample_is_fresh_locked(active_sample):
            return

        for candidate in (preferred, "serial", "wireless", "api"):
            if candidate == active:
                continue
            sample = self._last_samples.get(candidate)
            if self._sample_is_fresh_locked(sample):
                self._state["active_source"] = candidate
                self._record_event_locked(
                    f"Switched active source from {active} to {candidate} due to stale data"
                )
                return

    def set_mode(self, mode: str) -> None:
        with self._lock:
            self._state["mode"] = mode
            preferred = self._preferred_source_locked()
            self._state["active_source"] = preferred

    def clear_runtime(self) -> None:
        with self._lock:
            self._state["mode"] = "idle"
            self._state["active_source"] = None
            self._state["connected"] = False
            self._state["serial"].update(
                {
                    "connected": False,
                    "port": None,
                    "baud": None,
                    "last_error": None,
                    "updated_at": now_ms(),
                }
            )
            self._state["wireless"].update(
                {
                    "connected": False,
                    "device_id": None,
                    "last_error": None,
                    "updated_at": now_ms(),
                }
            )
            self._state["cursor"].update(
                {
                    "last_sample": None,
                    "last_applied": None,
                    "sample_rate_hz": 0.0,
                    "queue_lag_ms": None,
                    "last_error": None,
                    "updated_at": now_ms(),
                }
            )
            self._state["agent_stats"] = {"serial": {}, "cursor": {}, "wireless": {}}
            self._state["last_error"] = None
            self._last_samples = {"serial": None, "wireless": None, "api": None}
            for sample_times in self._sample_times.values():
                sample_times.clear()

    def set_last_error(self, error: Optional[str]) -> None:
        with self._lock:
            self._state["last_error"] = error

    def set_serial_status(
        self,
        *,
        connected: bool,
        port: Optional[str] = None,
        baud: Optional[int] = None,
        last_error: Optional[str] = None,
    ) -> None:
        with self._lock:
            serial_state = self._state["serial"]
            serial_state["connected"] = connected
            if port is not None:
                serial_state["port"] = port
            if baud is not None:
                serial_state["baud"] = baud
            serial_state["last_error"] = last_error
            serial_state["updated_at"] = now_ms()
            self._update_connected_locked()

    def set_wireless_status(
        self,
        *,
        connected: bool,
        device_id: Optional[str] = None,
        last_error: Optional[str] = None,
    ) -> None:
        with self._lock:
            wireless_state = self._state["wireless"]
            wireless_state["connected"] = connected
            if device_id is not None:
                wireless_state["device_id"] = device_id
            wireless_state["last_error"] = last_error
            wireless_state["updated_at"] = now_ms()
            self._update_connected_locked()

    def ingest_cursor_sample(self, payload: Dict[str, Any], *, default_source: str = "serial") -> Dict[str, Any]:
        with self._lock:
            source = str(payload.get("source") or default_source)
            x = float(payload["x"])
            y = float(payload["y"])
            ts_ms = int(payload.get("ts_ms") or now_ms())
            seq = int(payload.get("seq") or self._next_seq_locked())

            sample: Dict[str, Any] = {
                "ts_ms": ts_ms,
                "x": x,
                "y": y,
                "source": source,
                "seq": seq,
            }
            if "confidence" in payload:
                sample["confidence"] = payload["confidence"]
            if "raw" in payload:
                sample["raw"] = payload["raw"]

            self._last_samples[source] = sample
            self._sample_times.setdefault(source, deque(maxlen=90)).append(ts_ms)

            self._state["cursor"]["last_sample"] = sample
            self._state["cursor"]["updated_at"] = now_ms()

            if source == "serial":
                self._state["serial"]["connected"] = True
                self._state["serial"]["updated_at"] = now_ms()
            elif source == "wireless":
                self._state["wireless"]["connected"] = True
                self._state["wireless"]["updated_at"] = now_ms()

            active_source = self._state["active_source"] or source
            timestamps = self._sample_times.get(active_source) or deque(maxlen=90)
            if len(timestamps) >= 2:
                elapsed = max(1, timestamps[-1] - timestamps[0])
                self._state["cursor"]["sample_rate_hz"] = round((len(timestamps) - 1) / (elapsed / 1000.0), 2)

            self._fallback_active_source_locked()
            self._update_connected_locked()
            return copy.deepcopy(sample)

    def get_latest_cursor(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            self._fallback_active_source_locked()
            active = self._state["active_source"]
            if not active:
                return None
            sample = self._last_samples.get(active)
            if not self._sample_is_fresh_locked(sample):
                return None
            return copy.deepcopy(sample)

    def set_cursor_applied(self, sample: Dict[str, Any], queue_lag_ms: Optional[int]) -> None:
        with self._lock:
            self._state["cursor"]["last_applied"] = {
                "ts_ms": now_ms(),
                "sample_ts_ms": sample.get("ts_ms"),
                "seq": sample.get("seq"),
                "x": sample.get("x"),
                "y": sample.get("y"),
            }
            self._state["cursor"]["queue_lag_ms"] = queue_lag_ms
            self._state["cursor"]["updated_at"] = now_ms()

    def set_agent_stats(self, agent: str, stats: Dict[str, Any]) -> None:
        with self._lock:
            payload = copy.deepcopy(stats)
            payload.setdefault("ts_ms", now_ms())
            self._state["agent_stats"][agent] = payload

            if agent == "serial":
                if "connected" in payload:
                    self._state["serial"]["connected"] = bool(payload["connected"])
                if "last_error" in payload:
                    self._state["serial"]["last_error"] = payload["last_error"]
                self._state["serial"]["updated_at"] = now_ms()
            elif agent == "cursor":
                if "last_error" in payload:
                    self._state["cursor"]["last_error"] = payload["last_error"]
                if "queue_lag_ms" in payload:
                    self._state["cursor"]["queue_lag_ms"] = payload["queue_lag_ms"]
            elif agent == "wireless":
                if "connected" in payload:
                    self._state["wireless"]["connected"] = bool(payload["connected"])
                if "last_error" in payload:
                    self._state["wireless"]["last_error"] = payload["last_error"]
                self._state["wireless"]["updated_at"] = now_ms()

            if payload.get("last_error"):
                self._state["last_error"] = payload.get("last_error")
            self._update_connected_locked()

    def set_calibration_session(self, session: Optional[Dict[str, Any]]) -> None:
        with self._lock:
            if session is None:
                self._state["calibration"] = {"state": "idle", "session": None}
                return
            self._state["calibration"] = {
                "state": session.get("state", "idle"),
                "session": copy.deepcopy(session),
            }

    def get_cursor_params(self, prefs: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            return {
                "horizontal_sensitivity": prefs.get("horizontal_sensitivity", 50),
                "vertical_sensitivity": prefs.get("vertical_sensitivity", 50),
                "connection_method": prefs.get("connection_method", ""),
                "calibration_data": prefs.get("calibration_data", []),
                "active_source": self._state["active_source"],
                "mode": self._state["mode"],
            }

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            self._fallback_active_source_locked()
            self._update_connected_locked()
            state = copy.deepcopy(self._state)
            state["sources"] = {
                name: copy.deepcopy(sample) for name, sample in self._last_samples.items() if sample is not None
            }
            return state
