"""Calibration session state machine."""

from __future__ import annotations

import copy
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from app.prefs_utils import load_prefs, save_prefs
from app.services.runtime_store import RuntimeStore


def now_ms() -> int:
    return int(time.time() * 1000)


class CalibrationService:
    def __init__(self, runtime_store: RuntimeStore) -> None:
        self._lock = threading.RLock()
        self._runtime_store = runtime_store
        self._session: Optional[Dict[str, Any]] = None

    def _sync_runtime_locked(self) -> None:
        self._runtime_store.set_calibration_session(copy.deepcopy(self._session))

    def start_session(self, *, total_nodes: int = 9, node_order: Optional[List[int]] = None) -> Dict[str, Any]:
        with self._lock:
            if node_order is None:
                node_order = list(range(total_nodes))
            self._session = {
                "session_id": str(uuid.uuid4()),
                "state": "running",
                "total_nodes": int(total_nodes),
                "node_order": list(node_order),
                "active_node_index": 0,
                "completed_nodes": [],
                "started_at": now_ms(),
                "completed_at": None,
                "aborted_at": None,
                "node_events": [],
            }
            self._sync_runtime_locked()
            return copy.deepcopy(self._session)

    def get_session(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._session)

    def record_node(self, *, session_id: str, node_index: int, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        with self._lock:
            if not self._session or self._session.get("state") != "running":
                raise ValueError("No running calibration session")
            if session_id != self._session.get("session_id"):
                raise ValueError("Invalid calibration session")

            completed = self._session["completed_nodes"]
            if node_index not in completed:
                completed.append(node_index)

            self._session["active_node_index"] = min(
                len(completed),
                max(0, self._session["total_nodes"] - 1),
            )
            self._session["node_events"].append(
                {
                    "ts_ms": now_ms(),
                    "node_index": node_index,
                    "data": data or {},
                }
            )

            self._sync_runtime_locked()
            return copy.deepcopy(self._session)

    def complete_session(
        self,
        *,
        session_id: str,
        calibration_data: Optional[List[Dict[str, Any]]] = None,
        timestamp: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self._lock:
            if not self._session:
                raise ValueError("No calibration session")
            if session_id != self._session.get("session_id"):
                raise ValueError("Invalid calibration session")

            self._session["state"] = "completed"
            self._session["completed_at"] = now_ms()
            self._session["active_node_index"] = max(0, self._session["total_nodes"] - 1)

            prefs = load_prefs()
            prefs["calibration_data"] = calibration_data or self._session.get("node_events", [])
            prefs["calibration_timestamp"] = timestamp or now_ms()
            prefs["has_onboarded"] = True
            save_prefs(prefs)

            self._sync_runtime_locked()
            return copy.deepcopy(self._session)

    def abort_session(self, *, reason: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            if not self._session:
                return None
            self._session["state"] = "aborted"
            self._session["aborted_at"] = now_ms()
            if reason:
                self._session["abort_reason"] = reason
            self._sync_runtime_locked()
            return copy.deepcopy(self._session)

    def complete_legacy_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            if not self._session:
                self.start_session(total_nodes=9)
            session_id = self._session["session_id"]
            return self.complete_session(
                session_id=session_id,
                calibration_data=payload.get("calibration_data", []),
                timestamp=payload.get("timestamp"),
            )
