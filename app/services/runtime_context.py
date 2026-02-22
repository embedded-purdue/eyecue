"""Shared runtime singletons for routes."""

from __future__ import annotations

from app.services.agent_supervisor import AgentSupervisor
from app.services.calibration_service import CalibrationService
from app.services.runtime_store import RuntimeStore


runtime_store = RuntimeStore()
agent_supervisor = AgentSupervisor(runtime_store)
calibration_service = CalibrationService(runtime_store)
