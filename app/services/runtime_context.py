"""Shared runtime singletons for routes."""

from __future__ import annotations

from app.services.agent_supervisor import AgentSupervisor
from app.services.calibration_service import CalibrationService
from app.services.runtime_store import RuntimeStore
from app.services.wireless_video_service import WirelessVideoService


runtime_store = RuntimeStore()
agent_supervisor = AgentSupervisor(runtime_store)
calibration_service = CalibrationService(runtime_store)

try:
    from app.services.contour_pupil_processor import ContourPupilFrameProcessor

    wireless_video_service = WirelessVideoService(
        runtime_store,
        processor=ContourPupilFrameProcessor(),
        processor_name="contour_pupil",
        processor_ready=True,
        processor_error=None,
    )
except Exception as exc:
    wireless_video_service = WirelessVideoService(
        runtime_store,
        processor=None,
        processor_name="contour_pupil",
        processor_ready=False,
        processor_error=str(exc),
    )
