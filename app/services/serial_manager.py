"""
Serial manager scaffold for ESP32 communication.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional

from .. import serial_connect


class SerialManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ser = None
        self._reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.latest_cursor: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None
        self.connected_port: Optional[str] = None

    def list_ports(self) -> List[Dict[str, str]]:
        ports = serial_connect.list_serial_ports()
        results: List[Dict[str, str]] = []
        for p in ports:
            results.append(
                {
                    "device": getattr(p, "device", ""),
                    "description": getattr(p, "description", ""),
                    "hwid": getattr(p, "hwid", ""),
                }
            )
        return results

    def connect(self, port: str, ssid: str, password: str, baud: int = serial_connect.BAUD) -> None:
        self.disconnect()
        ser = None
        try:
            ser = serial_connect.open_serial(port, baud=baud)
            serial_connect.send_wifi_credentials(ser, ssid, password)
        except Exception as exc:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass
            self.last_error = str(exc)
            raise

        with self._lock:
            self._ser = ser
            self.connected_port = port
            self.last_error = None
            self._stop_event.clear()
            self._reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader_thread.start()

    def disconnect(self) -> None:
        with self._lock:
            self._stop_event.set()
            ser = self._ser
            thread = self._reader_thread
            self._ser = None
            self._reader_thread = None
            self.connected_port = None

        if thread is not None:
            thread.join(timeout=1.0)
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    def status(self) -> Dict[str, Any]:
        with self._lock:
            connected = bool(self._ser and getattr(self._ser, "is_open", False))
            return {
                "connected": connected,
                "port": self.connected_port,
                "last_error": self.last_error,
            }

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            ser = self._ser
            if ser is None:
                break
            try:
                raw = ser.readline()
            except Exception as exc:
                self.last_error = str(exc)
                break
            if not raw:
                continue
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and "x" in data and "y" in data:
                self.latest_cursor = data


serial_manager = SerialManager()
