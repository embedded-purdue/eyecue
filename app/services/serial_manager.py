"""Compatibility wrapper around the new runtime supervisor.

This module is kept so older imports do not break.
"""

from __future__ import annotations

from typing import Any, Dict, List

from app import serial_connect
from app.services.runtime_context import agent_supervisor, runtime_store


class SerialManager:
    def list_ports(self) -> List[Dict[str, str]]:
        ports = serial_connect.list_serial_ports()
        return [
            {
                "device": getattr(p, "device", ""),
                "description": getattr(p, "description", ""),
                "hwid": getattr(p, "hwid", ""),
            }
            for p in ports
        ]

    def connect(self, port: str, ssid: str, password: str, baud: int = serial_connect.BAUD) -> None:
        agent_supervisor.start_runtime(
            mode="serial",
            port=port,
            ssid=ssid,
            password=password,
            baud=baud,
        )

    def disconnect(self) -> None:
        agent_supervisor.stop_serial_agent()

    def status(self) -> Dict[str, Any]:
        state = runtime_store.get_state()
        serial_state = state.get("serial", {})
        wireless_state = state.get("wireless", {})
        return {
            "connected": serial_state.get("connected", False),
            "port": serial_state.get("port"),
            "baud_rate": serial_state.get("baud"),
            "last_error": serial_state.get("last_error"),
            "wifi_connected": wireless_state.get("connected", False),
            "wifi_ssid": None,
            "wifi_ip": None,
            "camera_ready": state.get("connected", False),
        }


serial_manager = SerialManager()
