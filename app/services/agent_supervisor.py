"""Agent lifecycle supervisor for serial and cursor worker threads."""

from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from app.config import INTERNAL_BASE_URL
from app.services.cursor_agent import CursorAgent
from app.services.runtime_store import RuntimeStore
from app.services.serial_agent import SerialAgent


class AgentSupervisor:
    def __init__(self, runtime_store: RuntimeStore) -> None:
        self._lock = threading.RLock()
        self._runtime_store = runtime_store
        self._serial_agent: Optional[SerialAgent] = None
        self._cursor_agent: Optional[CursorAgent] = None

    def start_serial_agent(
        self,
        *,
        port: str,
        ssid: Optional[str],
        password: Optional[str],
        baud: int,
        mode: str,
    ) -> None:
        self.stop_serial_agent()
        agent = SerialAgent(
            port=port,
            ssid=ssid,
            password=password,
            baud=baud,
            mode=mode,
            base_url=INTERNAL_BASE_URL,
        )
        agent.start()
        with self._lock:
            self._serial_agent = agent
        self._runtime_store.set_serial_status(connected=False, port=port, baud=baud)

    def stop_serial_agent(self) -> None:
        with self._lock:
            agent = self._serial_agent
            self._serial_agent = None
        if agent:
            agent.stop()
        self._runtime_store.set_serial_status(connected=False)

    def start_cursor_agent(self) -> None:
        self.stop_cursor_agent()
        agent = CursorAgent(base_url=INTERNAL_BASE_URL)
        agent.start()
        with self._lock:
            self._cursor_agent = agent

    def stop_cursor_agent(self) -> None:
        with self._lock:
            agent = self._cursor_agent
            self._cursor_agent = None
        if agent:
            agent.stop()

    def start_runtime(
        self,
        *,
        mode: str,
        port: Optional[str],
        ssid: Optional[str],
        password: Optional[str],
        baud: int,
    ) -> Dict[str, Any]:
        self.stop_runtime(clear=False)
        self._runtime_store.clear_runtime()

        self._runtime_store.set_mode(mode)
        self.start_cursor_agent()

        if mode in {"serial", "wired"}:
            if not port:
                raise ValueError("port is required for serial/wired mode")
            self.start_serial_agent(port=port, ssid=ssid, password=password, baud=baud, mode=mode)
        elif mode == "wifi" and port:
            # Optional serial provisioning/fallback while wireless mode is active.
            self.start_serial_agent(port=port, ssid=ssid, password=password, baud=baud, mode=mode)
        else:
            self._runtime_store.set_serial_status(connected=False)

        return self._runtime_store.get_state()

    def stop_runtime(self, *, clear: bool = True) -> Dict[str, Any]:
        self.stop_serial_agent()
        self.stop_cursor_agent()
        if clear:
            self._runtime_store.clear_runtime()
        return self._runtime_store.get_state()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "serial_agent_running": bool(self._serial_agent and self._serial_agent.is_running()),
                "cursor_agent_running": bool(self._cursor_agent and self._cursor_agent.is_running()),
            }
