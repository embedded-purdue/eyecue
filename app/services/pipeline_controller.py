"""Minimal runtime controller for serial provisioning and MJPEG CV pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from app import serial_connect
from app.config import (
    BYPASS_SERIAL,
    MJPEG_PATH_CANDIDATES,
    SERIAL_ACK_RETRIES,
    SERIAL_ACK_TIMEOUT_S,
    SERIAL_DEBUG,
    SERIAL_HANDSHAKE_ATTEMPTS,
    SERIAL_HANDSHAKE_ATTEMPT_TIMEOUT_S,
    STREAM_RETRY_DELAY_S,
)

try:
    import pyautogui
except Exception:  # pragma: no cover - optional runtime dependency
    pyautogui = None

try:
    from app.services.contour_pupil_processor import ContourPupilFrameProcessor
except Exception:  # pragma: no cover - optional runtime dependency
    ContourPupilFrameProcessor = None


def now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class AlertEntry:
    id: int
    ts_ms: int
    level: str
    message: str


@dataclass
class PipelineState:
    phase: str = "idle"
    ssid: str = ""
    serial_port: str = ""
    esp32_ip: Optional[str] = None
    stream_url: Optional[str] = None
    tracking_enabled: bool = False
    frames_processed: int = 0
    last_frame_ts_ms: Optional[int] = None
    last_error: Optional[str] = None
    alerts: List[AlertEntry] = field(default_factory=list)


class PipelineController:
    """Owns the single background worker for provisioning and stream processing."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._alert_id = 0
        self._state = PipelineState()

        self._processor = None
        self._processor_error: Optional[str] = None
        if ContourPupilFrameProcessor is None:
            self._processor_error = "contour processor unavailable"
        else:
            try:
                self._processor = ContourPupilFrameProcessor()
            except Exception as exc:  # pragma: no cover - runtime dependency guard
                self._processor_error = str(exc)

    def _append_alert_locked(self, level: str, message: str) -> None:
        self._alert_id += 1
        self._state.alerts.append(AlertEntry(id=self._alert_id, ts_ms=now_ms(), level=level, message=message))
        if len(self._state.alerts) > 100:
            self._state.alerts = self._state.alerts[-100:]

    def _emit_serial_debug(self, message: str) -> None:
        if not SERIAL_DEBUG:
            return
        print(f"[serial] {message}", flush=True)
        with self._lock:
            self._append_alert_locked("info", message)

    def _set_error_locked(self, message: str) -> None:
        if self._state.last_error == message:
            return
        self._state.last_error = message
        self._append_alert_locked("error", message)

    def _snapshot_locked(self) -> Dict[str, Any]:
        payload = asdict(self._state)
        payload["alerts"] = [asdict(entry) for entry in self._state.alerts]
        return payload

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def set_tracking(self, enabled: bool) -> Dict[str, Any]:
        with self._lock:
            self._state.tracking_enabled = bool(enabled)
            message = "Cursor tracking enabled." if self._state.tracking_enabled else "Cursor tracking disabled."
            self._append_alert_locked("info", message)
            return self._snapshot_locked()

    def connect(self, *, ssid: str, password: str, serial_port: str, baud: int = serial_connect.BAUD) -> Dict[str, Any]:
        ssid = str(ssid or "").strip()
        password = str(password or "")
        serial_port = str(serial_port or "").strip()
        if not ssid:
            raise ValueError("ssid is required")
        if not serial_port:
            raise ValueError("serial_port is required")

        self._stop_worker()

        with self._lock:
            tracking_enabled = self._state.tracking_enabled
            self._stop_event.clear()
            self._state = PipelineState(
                phase="connecting_esp32",
                ssid=ssid,
                serial_port=serial_port,
                tracking_enabled=tracking_enabled,
            )
            self._append_alert_locked("info", "Connecting to ESP32…")

            self._worker = threading.Thread(
                target=self._run_pipeline,
                kwargs={"ssid": ssid, "password": password, "serial_port": serial_port, "baud": int(baud)},
                daemon=True,
                name="pipeline-controller",
            )
            self._worker.start()
            return self._snapshot_locked()

    def stop(self) -> Dict[str, Any]:
        self._stop_worker()
        with self._lock:
            self._state.phase = "idle"
            self._state.esp32_ip = None
            self._state.stream_url = None
            self._state.last_error = None
            self._append_alert_locked("info", "Pipeline stopped.")
            return self._snapshot_locked()

    def _stop_worker(self) -> None:
        with self._lock:
            worker = self._worker
            self._worker = None
            self._stop_event.set()
        if worker and worker.is_alive():
            worker.join(timeout=3.0)

    def _run_serial_handshake_attempt(
        self,
        ser: Any,
        *,
        ssid: str,
        password: str,
        timeout_s: float,
    ) -> Tuple[bool, Optional[str], Optional[str], str, List[str]]:
        """Two-phase handshake.

        Phase 1: send WIFI_CONFIG with quick ACK retries.
        Phase 2: after ACK, wait longer for OK <ip> / ERR.
        """
        nonce = serial_connect.make_nonce()
        all_lines: List[str] = []
        saw_ack = False
        line_logger = (lambda line: self._emit_serial_debug(f"SERIAL RX {line}")) if SERIAL_DEBUG else None

        for ack_attempt in range(1, max(1, SERIAL_ACK_RETRIES) + 1):
            tx_line = serial_connect.send_wifi_config_command(ser, ssid, password, nonce)
            self._emit_serial_debug(
                f"SERIAL TX ack_attempt={ack_attempt}/{max(1, SERIAL_ACK_RETRIES)} {tx_line}"
            )
            ack_seen, ip_addr, device_error, lines = serial_connect.read_handshake_signals(
                ser,
                expected_nonce=nonce,
                timeout_s=SERIAL_ACK_TIMEOUT_S,
                line_logger=line_logger,
            )
            all_lines.extend(lines)

            if device_error:
                return saw_ack or ack_seen, None, device_error, nonce, all_lines
            if ip_addr:
                return saw_ack or ack_seen, ip_addr, None, nonce, all_lines
            if ack_seen:
                saw_ack = True
                break

        if not saw_ack:
            return False, None, None, nonce, all_lines

        self._emit_serial_debug(f"SERIAL ACK nonce={nonce}; waiting for OK/ERR timeout={timeout_s}s")
        _ack_seen, ip_addr, device_error, lines = serial_connect.read_handshake_signals(
            ser,
            expected_nonce=nonce,
            timeout_s=timeout_s,
            line_logger=line_logger,
        )
        all_lines.extend(lines)
        return True, ip_addr, device_error, nonce, all_lines

    def _run_pipeline(self, *, ssid: str, password: str, serial_port: str, baud: int) -> None:
        try:
            ip_addr = self._provision_wifi(ssid=ssid, password=password, serial_port=serial_port, baud=baud)
            if self._stop_event.is_set():
                return
            self._stream_loop(ip_addr)
        except Exception as exc:
            if self._stop_event.is_set():
                return
            with self._lock:
                self._state.phase = "error"
                self._set_error_locked(str(exc))

    def _provision_wifi(self, *, ssid: str, password: str, serial_port: str, baud: int) -> str:
        if BYPASS_SERIAL:
            return "127.0.0.1:5052"

        with self._lock:
            self._state.phase = "provisioning"
            self._state.last_error = None

        with serial_connect.open_serial(serial_port, baud=baud) as ser:
            last_status = "no response"
            for attempt in range(1, max(1, SERIAL_HANDSHAKE_ATTEMPTS) + 1):
                if self._stop_event.is_set():
                    raise RuntimeError("serial provisioning canceled")

                try:
                    ser.reset_input_buffer()
                except Exception:
                    pass

                with self._lock:
                    self._append_alert_locked(
                        "info",
                        f"Sending Wi-Fi config over serial (attempt {attempt}/{SERIAL_HANDSHAKE_ATTEMPTS})…",
                    )

                saw_ack, ip_addr, device_error, nonce, lines = self._run_serial_handshake_attempt(
                    ser,
                    ssid=ssid,
                    password=password,
                    timeout_s=SERIAL_HANDSHAKE_ATTEMPT_TIMEOUT_S,
                )

                if device_error:
                    raise RuntimeError(f"ESP32 reported error: {device_error}")

                if ip_addr:
                    with self._lock:
                        self._append_alert_locked(
                            "info",
                            f"Serial handshake complete (ack_seen={saw_ack}, nonce={nonce}).",
                        )
                    break

                if saw_ack:
                    last_status = f"ACK seen but no OK <ip> yet (rx_lines={len(lines)})"
                else:
                    last_status = f"no ACK/OK seen (rx_lines={len(lines)})"

                with self._lock:
                    self._append_alert_locked(
                        "warning",
                        f"No complete serial response ({last_status}). Retrying…",
                    )
            else:
                raise RuntimeError(
                    f"Failed serial provisioning after {SERIAL_HANDSHAKE_ATTEMPTS} attempts ({last_status})."
                )

        with self._lock:
            self._state.phase = "wifi_connected"
            self._state.esp32_ip = ip_addr
            self._append_alert_locked("info", "Network connected. Safe to unplug device.")
        return ip_addr

    def _stream_loop(self, ip_addr: str) -> None:
        base_url = f"http://{ip_addr}"
        path_candidates = MJPEG_PATH_CANDIDATES or ("/stream",)

        while not self._stop_event.is_set():
            with self._lock:
                self._state.phase = "stream_connecting"
                self._append_alert_locked("info", "Attempting to open camera stream…")

            last_error: Optional[str] = None
            connected = False

            for path in path_candidates:
                if self._stop_event.is_set():
                    return
                candidate_path = path if path.startswith("/") else f"/{path}"
                stream_url = f"{base_url}{candidate_path}"
                try:
                    with requests.get(stream_url, stream=True, timeout=(3.0, 5.0)) as response:
                        if response.status_code != 200:
                            last_error = f"Stream unavailable at {stream_url} (HTTP {response.status_code})"
                            continue

                        connected = True
                        with self._lock:
                            self._state.phase = "streaming"
                            self._state.stream_url = stream_url
                            self._state.last_error = None
                            self._append_alert_locked("info", "Camera stream connected.")
                        self._consume_stream(response)
                except Exception as exc:
                    last_error = str(exc)

                if connected:
                    break

            if self._stop_event.is_set():
                return

            with self._lock:
                self._state.phase = "stream_retrying"
                if last_error:
                    self._state.last_error = last_error
                self._append_alert_locked("warning", "Camera stream lost. Retrying…")
            self._stop_event.wait(max(0.1, STREAM_RETRY_DELAY_S))

    def _consume_stream(self, response: requests.Response) -> None:
        buffer = bytearray()

        for chunk in response.iter_content(chunk_size=4096):
            if self._stop_event.is_set():
                return
            if not chunk:
                continue

            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                if start < 0:
                    if len(buffer) > 2:
                        del buffer[:-2]
                    break

                end = buffer.find(b"\xff\xd9", start + 2)
                if end < 0:
                    if start > 0:
                        del buffer[:start]
                    break

                frame_bytes = bytes(buffer[start:end + 2])
                del buffer[:end + 2]
                self._process_frame(frame_bytes)

    def _process_frame(self, frame_bytes: bytes) -> None:
        if not frame_bytes:
            return

        if self._processor is None:
            with self._lock:
                self._set_error_locked(
                    f"CV processor unavailable: {self._processor_error or 'unknown initialization error'}"
                )
            return

        try:
            result = self._processor.process_frame(frame_bytes, {"frame_ts_ms": now_ms()}) or {}
        except Exception as exc:
            with self._lock:
                self._set_error_locked(f"CV processing failed: {exc}")
            return

        cursor = result.get("cursor")
        # print(cursor)
        should_track = False
        with self._lock:
            should_track = self._state.tracking_enabled
            self._state.frames_processed += 1
            self._state.last_frame_ts_ms = now_ms()
            if result.get("error"):
                self._state.last_error = str(result.get("error"))

        if should_track and isinstance(cursor, dict):
            self._apply_cursor(cursor)

    def _apply_cursor(self, cursor: Dict[str, int | float]) -> None:
        if pyautogui is None:
            with self._lock:
                self._set_error_locked("pyautogui is unavailable for cursor movement.")
            return

        try:
            x = cursor.get("x")
            y = cursor.get("y")
            confidence = cursor.get("confidence")

            assert x is not None
            assert y is not None

            x = float(x)
            y = float(y)

            if SERIAL_DEBUG:
                print(f"[cursor] moveTo x={x} y={y} confidence={confidence}", flush=True)
            pyautogui.moveTo(x, y)
        except Exception as exc:
            with self._lock:
                self._set_error_locked(f"Cursor update failed: {exc}")
